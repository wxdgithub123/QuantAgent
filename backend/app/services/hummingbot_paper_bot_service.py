"""
Hummingbot Paper Bot Service

v1.2.1 阶段：配置预览，不启动 Bot，不执行真实交易。
v1.2.2 阶段：启动 Paper Bot，使用虚拟资金模拟运行。
v1.2.3 阶段：查看 Paper Bot 状态、模拟订单、模拟持仓、日志。

核心功能：
1. 接收用户提交的 Paper Bot 配置参数
2. 进行后端安全校验
3. 检查敏感字段（api_key, secret 等）
4. 检查危险模式字段（mode=live, testnet 等）
5. 生成标准化 config_preview JSON
6. 调用 Hummingbot API 启动 Paper Bot（v1.2.2）
7. 查看 Paper Bot 状态、订单、持仓、日志（v1.2.3）
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.schemas.hummingbot_paper_bot import (
    PaperBotPreviewRequest,
    PaperBotPreviewResponse,
    PaperBotPreviewData,
    ConfigPreview,
    PaperBotStartResponse,
    PaperBotStartData,
)

# 获取 logger
logger = logging.getLogger(__name__)


# ── 敏感字段黑名单 ──────────────────────────────────────────────────────────────

SENSITIVE_FIELD_PATTERNS = [
    # API Key / Secret 相关
    "api_key",
    "apikey",
    "apiSecret",
    "api_secret",
    "secret",
    "private_key",
    "privateKey",
    "exchange_secret",
    "exchangeSecret",
    # 认证相关
    "password",
    "passphrase",
    "token",
    "access_token",
    "refresh_token",
    # 钱包相关
    "wallet_private_key",
    "wallet_privatekey",
    "mnemonic",
    "seed_phrase",
    "seedphrase",
    # 其他危险字段
    "real_trading",
    "live_trading",
    "testnet",
]

# 危险模式值
DANGEROUS_MODE_VALUES = [
    "live",
    "testnet",
]


class HummingbotPaperBotValidationError(Exception):
    """校验错误异常"""
    def __init__(self, message: str, error_type: str = "validation_error"):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


def _flatten_dict(data: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    递归扁平化字典，用于检测嵌套的敏感字段。

    例如：
        {"api_key": "xxx"} -> {"api_key": "xxx"}
        {"nested": {"api_key": "xxx"}} -> {"nested.api_key": "xxx"}
    """
    items: List[tuple] = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_key = f"{parent_key}{sep}{i}"
            items.extend(_flatten_dict(item, new_key, sep=sep).items())
    else:
        items.append((parent_key, data))
    return dict(items)


def _check_sensitive_fields(request_data: Dict[str, Any]) -> Optional[str]:
    """
    递归检查请求体中的敏感字段。

    Args:
        request_data: 请求体字典

    Returns:
        错误信息字符串，如果无错误则返回 None
    """
    flat_data = _flatten_dict(request_data)

    for key in flat_data.keys():
        key_lower = key.lower()
        for pattern in SENSITIVE_FIELD_PATTERNS:
            if pattern.lower() in key_lower:
                return f"Paper Bot 配置预览不允许提交任何 API Key、Secret、Token 或私钥字段。检测到敏感字段: '{key}'"

    return None


def _check_dangerous_modes(request_data: Dict[str, Any]) -> Optional[str]:
    """
    检查请求体中是否包含危险模式值。

    Args:
        request_data: 请求体字典

    Returns:
        错误信息字符串，如果无错误则返回 None
    """
    flat_data = _flatten_dict(request_data)

    # 检查 mode 字段
    mode_value = flat_data.get("mode", "")
    if isinstance(mode_value, str) and mode_value.lower() in DANGEROUS_MODE_VALUES:
        return f"检测到危险配置: mode='{mode_value}'。当前阶段仅支持 Paper Bot，不支持 Testnet 或 Live。"

    # 检查 live_trading 字段
    live_trading_value = flat_data.get("live_trading")
    if live_trading_value is True or str(live_trading_value).lower() == "true":
        return "检测到危险配置: live_trading=true。当前阶段仅支持 Paper Bot，不支持真实交易。"

    # 检查 testnet 字段
    testnet_value = flat_data.get("testnet")
    if testnet_value is True or str(testnet_value).lower() == "true":
        return "检测到危险配置: testnet=true。当前阶段仅支持 Paper Bot，不支持 Testnet。"

    # 检查 real_trading 字段
    real_trading_value = flat_data.get("real_trading")
    if real_trading_value is True or str(real_trading_value).lower() == "true":
        return "检测到危险配置: real_trading=true。当前阶段仅支持 Paper Bot，不支持真实交易。"

    return None


def _validate_strategy_params(request: PaperBotPreviewRequest) -> None:
    """
    校验策略特定参数。

    Args:
        request: 校验后的请求对象

    Raises:
        HummingbotPaperBotValidationError: 校验失败时抛出
    """
    if request.strategy_type.value == "grid":
        # grid 策略必须提供 grid_spacing_pct
        if request.grid_spacing_pct is None or request.grid_spacing_pct <= 0:
            raise HummingbotPaperBotValidationError(
                "grid 策略必须提供有效的 grid_spacing_pct（> 0）",
                error_type="strategy_validation"
            )

        # grid_levels 默认 20（已在 schema 中设置）
        # 这里可以添加额外校验
        if request.grid_levels < 2 or request.grid_levels > 200:
            raise HummingbotPaperBotValidationError(
                "grid_levels 必须在 2-200 之间",
                error_type="strategy_validation"
            )

    elif request.strategy_type.value == "position_executor":
        # position_executor 策略的 grid_spacing_pct 和 grid_levels 是可选的
        # spread_pct 是可选的
        pass


def _validate_order_amount(request: PaperBotPreviewRequest) -> None:
    """
    校验 order_amount <= paper_initial_balance。

    Args:
        request: 校验后的请求对象

    Raises:
        HummingbotPaperBotValidationError: 校验失败时抛出
    """
    if request.order_amount > request.paper_initial_balance:
        raise HummingbotPaperBotValidationError(
            f"单笔订单金额 (order_amount={request.order_amount}) 不能大于初始资金 (paper_initial_balance={request.paper_initial_balance})",
            error_type="validation_error"
        )

    # 建议检查：order_amount 不应超过 paper_initial_balance 的 50%
    if request.order_amount > request.paper_initial_balance * 0.5:
        # 这个只作为警告，不阻止生成预览
        pass


def _build_config_preview(request: PaperBotPreviewRequest) -> Dict[str, Any]:
    """
    构建标准化 config_preview 字典。

    Args:
        request: 校验后的请求对象

    Returns:
        config_preview 字典
    """
    # 构建风险配置
    risk_config = {
        "stop_loss_pct": request.stop_loss_pct or 0,
        "take_profit_pct": request.take_profit_pct or 0,
        "max_runtime_minutes": request.max_runtime_minutes,
    }

    # 构建策略参数
    strategy_params: Dict[str, Any] = {}

    if request.strategy_type.value == "position_executor":
        if request.spread_pct is not None:
            strategy_params["spread_pct"] = request.spread_pct

    elif request.strategy_type.value == "grid":
        strategy_params["grid_spacing_pct"] = request.grid_spacing_pct
        strategy_params["grid_levels"] = request.grid_levels or 20

    # 笔记
    notes = [
        "当前配置仅用于 Paper Bot 预览。",
        "不会启动 Bot。",
        "不会执行真实交易。",
        "不会使用真实交易所 API Key。",
        f"策略类型: {request.strategy_type.value}",
        f"交易对: {request.trading_pair}",
    ]

    # 强制固定的字段（后端硬编码，不信任前端）
    config_preview = {
        "bot_name": request.bot_name,
        "mode": "paper",                           # 强制固定
        "live_trading": False,                     # 强制固定
        "testnet": False,                          # 强制固定
        "uses_real_exchange_account": False,        # 强制固定
        "requires_api_key": False,                  # 强制固定
        "strategy_type": request.strategy_type.value,
        "trading_pair": request.trading_pair,
        "paper_initial_balance": request.paper_initial_balance,
        "order_amount": request.order_amount,
        "risk": risk_config,
        "strategy_params": strategy_params,
        "notes": notes,
    }

    return config_preview


async def generate_paper_bot_preview(
    request: PaperBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> PaperBotPreviewResponse:
    """
    生成 Paper Bot 配置预览。

    完整校验流程：
    1. 检查敏感字段（递归）
    2. 检查危险模式值
    3. 校验策略参数
    4. 校验 order_amount
    5. 构建 config_preview

    本函数不调用任何 Hummingbot API，不启动 Bot。

    Args:
        request: Pydantic 校验后的请求对象
        raw_request_data: 原始请求体字典（用于检查 Pydantic 未验证的字段）

    Returns:
        PaperBotPreviewResponse: 预览响应
    """
    try:
        # ── Step 1: 检查敏感字段 ──────────────────────────────────────────────
        if raw_request_data:
            sensitive_error = _check_sensitive_fields(raw_request_data)
            if sensitive_error:
                return PaperBotPreviewResponse(
                    valid=False,
                    error=sensitive_error,
                )

        # ── Step 2: 检查危险模式值 ────────────────────────────────────────────
        if raw_request_data:
            mode_error = _check_dangerous_modes(raw_request_data)
            if mode_error:
                return PaperBotPreviewResponse(
                    valid=False,
                    error=mode_error,
                )

        # ── Step 3: 校验策略参数 ──────────────────────────────────────────────
        _validate_strategy_params(request)

        # ── Step 4: 校验 order_amount ─────────────────────────────────────────
        _validate_order_amount(request)

        # ── Step 5: 构建 config_preview ───────────────────────────────────────
        config_preview_dict = _build_config_preview(request)

        # 构建响应
        preview_data = PaperBotPreviewData(
            config_preview=ConfigPreview(**config_preview_dict),
            warnings=[
                "当前仅生成配置预览，尚未调用 Hummingbot API 启动 Bot。"
            ],
        )

        return PaperBotPreviewResponse(
            valid=True,
            data=preview_data,
        )

    except HummingbotPaperBotValidationError as e:
        return PaperBotPreviewResponse(
            valid=False,
            error=e.message,
        )
    except Exception as e:
        return PaperBotPreviewResponse(
            valid=False,
            error=f"生成预览时发生未知错误: {str(e)}",
        )


# ── v1.2.2: Paper Bot 启动功能 ─────────────────────────────────────────────────

PAPER_BOT_AVAILABLE = True  # 是否可以使用 Paper Bot 功能


async def _call_hummingbot_api(
    method: str,
    path: str,
    json_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    调用 Hummingbot API 的统一方法。

    Args:
        method: HTTP 方法
        path: API 路径
        json_data: 请求体

    Returns:
        API 响应

    Raises:
        Exception: API 调用失败时抛出
    """
    base_url = settings.HUMMINGBOT_API_URL.rstrip("/")
    url = f"{base_url}/{path.lstrip('/')}"

    username = settings.HUMMINGBOT_API_USERNAME
    password = settings.HUMMINGBOT_API_PASSWORD
    auth = None
    if username and password:
        auth = httpx.BasicAuth(username, password)

    async with httpx.AsyncClient(
        timeout=settings.HUMMINGBOT_API_TIMEOUT,
        follow_redirects=True,
    ) as client:
        response = await client.request(
            method=method,
            url=url,
            json=json_data,
            auth=auth,
        )

        if response.status_code == 401:
            raise Exception("Hummingbot API 认证失败")
        elif response.status_code == 404:
            raise Exception(f"Hummingbot API 路径不存在: {path}")
        elif not response.is_success:
            raise Exception(f"Hummingbot API 请求失败: HTTP {response.status_code}")

        try:
            return response.json()
        except Exception:
            return {"_raw": response.text}


def _log_paper_bot_operation(
    operation: str,
    bot_name: str,
    strategy_type: str,
    trading_pair: str,
    success: bool,
    error_message: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    记录 Paper Bot 操作日志。

    注意：日志中不记录任何敏感信息。
    """
    log_data = {
        "operation": operation,
        "bot_name": bot_name,
        "strategy_type": strategy_type,
        "trading_pair": trading_pair,
        "mode": "paper",
        "live_trading": False,
        "success": success,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    if error_message:
        log_data["error"] = error_message

    # 不记录敏感配置
    safe_config = {
        k: v for k, v in (config or {}).items()
        if k not in SENSITIVE_FIELD_PATTERNS and k not in ["password", "api_key", "secret"]
    }
    log_data["config"] = safe_config

    logger.info(f"Paper Bot Operation: {log_data}")


async def start_paper_bot(
    request: PaperBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> PaperBotStartResponse:
    """
    启动 Hummingbot Paper Bot。

    完整流程：
    1. 安全校验（与 preview 相同）
    2. 检测 Hummingbot API 可用性
    3. 构造 Paper Bot 配置
    4. 调用 Hummingbot API 启动 Bot
    5. 记录操作日志

    Args:
        request: Pydantic 校验后的请求对象
        raw_request_data: 原始请求体字典

    Returns:
        PaperBotStartResponse: 启动响应
    """
    try:
        # ── Step 1: 安全校验 ──────────────────────────────────────────────────
        if raw_request_data:
            sensitive_error = _check_sensitive_fields(raw_request_data)
            if sensitive_error:
                _log_paper_bot_operation(
                    operation="start_paper_bot",
                    bot_name=request.bot_name,
                    strategy_type=request.strategy_type.value,
                    trading_pair=request.trading_pair,
                    success=False,
                    error_message=sensitive_error,
                    config=raw_request_data,
                )
                return PaperBotStartResponse(
                    started=False,
                    error=sensitive_error,
                )

        if raw_request_data:
            mode_error = _check_dangerous_modes(raw_request_data)
            if mode_error:
                _log_paper_bot_operation(
                    operation="start_paper_bot",
                    bot_name=request.bot_name,
                    strategy_type=request.strategy_type.value,
                    trading_pair=request.trading_pair,
                    success=False,
                    error_message=mode_error,
                    config=raw_request_data,
                )
                return PaperBotStartResponse(
                    started=False,
                    error=mode_error,
                )

        _validate_strategy_params(request)
        _validate_order_amount(request)

        # ── Step 2: 检测 Hummingbot API 可用性 ────────────────────────────────
        hummingbot_response: Dict[str, Any] = {}
        api_available = True
        api_error: Optional[str] = None

        try:
            # 检查 Hummingbot API 是否在线
            status_result = await _call_hummingbot_api("GET", "/")
            hummingbot_response["status_check"] = status_result
        except Exception as e:
            api_available = False
            api_error = f"Hummingbot API 不可用: {str(e)}"
            logger.warning(f"Hummingbot API not available: {e}")

        # ── Step 3: 构造 Paper Bot 配置 ──────────────────────────────────────
        # 构建 config_preview（与 preview 相同）
        config_preview_dict = _build_config_preview(request)

        # 生成 Paper Bot ID
        paper_bot_id = f"paper_{request.bot_name}_{uuid.uuid4().hex[:8]}"

        # 记录到本地
        record_paper_bot(
            paper_bot_id=paper_bot_id,
            bot_name=request.bot_name,
            strategy_type=request.strategy_type.value,
            trading_pair=request.trading_pair,
            config=config_preview_dict,
        )

        # ── Step 4: 尝试调用 Hummingbot API 启动 Bot ─────────────────────────
        start_result: Dict[str, Any] = {}
        start_success = False

        if api_available:
            try:
                # 构造启动请求
                # 根据 Hummingbot API v1.0.1，支持 /bot-orchestration/deploy-v2-controllers
                # 使用 paper exchange connector
                start_payload = {
                    "instance_name": paper_bot_id,
                    "credentials_profile": "paper_account",  # Paper 账户
                    "controllers_config": [],  # 空控制器配置，稍后可以通过 controller API 配置
                    "headless": True,
                }

                # 尝试部署 V2 Controller
                deploy_result = await _call_hummingbot_api(
                    "POST",
                    "/bot-orchestration/deploy-v2-controllers",
                    json_data=start_payload,
                )
                start_result = deploy_result
                start_success = True

            except Exception as e:
                start_result = {"error": str(e)}
                start_success = False
                logger.warning(f"Failed to start Paper Bot via Hummingbot API: {e}")

        # ── Step 5: 构建响应 ─────────────────────────────────────────────────
        if start_success:
            # 更新状态为 running
            update_paper_bot_status(paper_bot_id, "running")

            start_data = PaperBotStartData(
                paper_bot_id=paper_bot_id,
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                status="starting",
                started_at=datetime.utcnow().isoformat() + "Z",
                hummingbot_response=hummingbot_response,
                config=config_preview_dict,
            )

            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=True,
                config=config_preview_dict,
            )

            return PaperBotStartResponse(
                started=True,
                data=start_data,
            )
        else:
            # API 不可用或启动失败，返回配置预览和清晰错误
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=False,
                error_message=api_error or "启动失败",
                config=config_preview_dict,
            )

            return PaperBotStartResponse(
                started=False,
                error=(
                    api_error or
                    "当前 Hummingbot API 版本未提供可用的 Paper Bot 启动接口，"
                    "或启动请求失败。请检查 Swagger 文档: http://localhost:8000/docs"
                ),
            )

    except HummingbotPaperBotValidationError as e:
        _log_paper_bot_operation(
            operation="start_paper_bot",
            bot_name=request.bot_name,
            strategy_type=request.strategy_type.value if hasattr(request, "strategy_type") else "unknown",
            trading_pair=request.trading_pair if hasattr(request, "trading_pair") else "unknown",
            success=False,
            error_message=e.message,
        )
        return PaperBotStartResponse(
            started=False,
            error=e.message,
        )
    except Exception as e:
        _log_paper_bot_operation(
            operation="start_paper_bot",
            bot_name=getattr(request, "bot_name", "unknown"),
            strategy_type=getattr(request, "strategy_type", "unknown"),
            trading_pair=getattr(request, "trading_pair", "unknown"),
            success=False,
            error_message=str(e),
        )
        return PaperBotStartResponse(
            started=False,
            error=f"启动 Paper Bot 时发生未知错误: {str(e)}",
        )


# ── v1.2.3: Paper Bot 查询功能 ────────────────────────────────────────────────

# ── 敏感字段过滤 ──────────────────────────────────────────────────────────────

SENSITIVE_KEYS = [
    # API Key / Secret
    "api_key", "apikey", "apiSecret", "api_secret", "secret",
    "private_key", "privateKey", "exchange_secret", "exchangeSecret",
    # 认证
    "password", "passphrase", "token", "access_token", "refresh_token",
    # 钱包
    "wallet_private_key", "wallet_privatekey", "mnemonic", "seed_phrase", "seedphrase",
    # 其他
    "real_trading",
]


def sanitize_data(data: Any, depth: int = 0) -> Any:
    """
    递归移除敏感字段（带深度限制）。

    Args:
        data: 任意类型数据
        depth: 当前递归深度

    Returns:
        过滤后的数据
    """
    if data is None:
        return None

    # 最大递归深度 20
    if depth > 20:
        return data

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sk in key_lower for sk in SENSITIVE_KEYS):
                result[key] = "***REDACTED***"
            else:
                result[key] = sanitize_data(value, depth + 1)
        return result

    if isinstance(data, list):
        if depth > 15:  # 列表嵌套限制更严格
            return data
        return [sanitize_data(item, depth + 1) for item in data[:200]]  # 最多200条

    return data


# ── Paper Bot 本地记录存储 ───────────────────────────────────────────────────

# 内存中的 Paper Bot 记录（仅用于演示，实际应使用数据库）
_paper_bot_records: Dict[str, Dict[str, Any]] = {}


def record_paper_bot(
    paper_bot_id: str,
    bot_name: str,
    strategy_type: str,
    trading_pair: str,
    config: Dict[str, Any],
) -> None:
    """记录 Paper Bot 启动信息"""
    _paper_bot_records[paper_bot_id] = {
        "paper_bot_id": paper_bot_id,
        "bot_name": bot_name,
        "strategy_type": strategy_type,
        "trading_pair": trading_pair,
        "mode": "paper",
        "live_trading": False,
        "testnet": False,
        "status": "starting",
        "started_at": datetime.utcnow().isoformat() + "Z",
        "config": config,
        "last_error": None,
    }


def update_paper_bot_status(
    paper_bot_id: str,
    status: str,
    last_error: Optional[str] = None,
) -> None:
    """更新 Paper Bot 状态"""
    if paper_bot_id in _paper_bot_records:
        _paper_bot_records[paper_bot_id]["status"] = status
        if last_error:
            _paper_bot_records[paper_bot_id]["last_error"] = last_error


def get_paper_bot_records() -> Dict[str, Dict[str, Any]]:
    """获取所有 Paper Bot 记录"""
    return _paper_bot_records


def get_paper_bot_record(paper_bot_id: str) -> Optional[Dict[str, Any]]:
    """获取单个 Paper Bot 记录"""
    return _paper_bot_records.get(paper_bot_id)


# ── Hummingbot API 调用封装 ─────────────────────────────────────────────────


# ── 查询函数 ─────────────────────────────────────────────────────────────────

async def get_paper_bots_list() -> Dict[str, Any]:
    """
    获取 Paper Bot 列表。

    数据来源：
    1. 优先返回本地记录的 Paper Bot
    2. 同时尝试获取 Hummingbot API 的 bots/containers

    Returns:
        Paper Bot 列表响应
    """
    try:
        # 获取本地记录
        local_records = get_paper_bot_records()

        # 尝试获取 Hummingbot API 状态
        hummingbot_bots = []
        hummingbot_source = None
        try:
            result = await _call_hummingbot_api("GET", "/bot-orchestration/status")
            hummingbot_source = "bot-orchestration"
            # 过滤并清理数据
            if result:
                hummingbot_bots = sanitize_data(result.get("data", []) or result)
        except Exception:
            # API 不可用，忽略
            pass

        # 合并结果
        bots = []

        # 添加本地记录的 Paper Bots
        for record in local_records.values():
            runtime = 0
            if record.get("started_at"):
                try:
                    started = datetime.fromisoformat(record["started_at"].replace("Z", "+00:00"))
                    runtime = int((datetime.now().astimezone() - started).total_seconds())
                except Exception:
                    pass

            bots.append({
                "paper_bot_id": record["paper_bot_id"],
                "bot_name": record["bot_name"],
                "strategy_type": record["strategy_type"],
                "trading_pair": record["trading_pair"],
                "mode": "paper",
                "live_trading": False,
                "testnet": False,
                "status": record["status"],
                "started_at": record["started_at"],
                "runtime_seconds": runtime,
                "source": "local",
            })

        # 添加从 Hummingbot API 获取的 bots（如果有）
        if hummingbot_bots and isinstance(hummingbot_bots, list):
            for bot in hummingbot_bots:
                bots.append({
                    "paper_bot_id": f"hummingbot_{bot.get('name', 'unknown')}",
                    "bot_name": bot.get("name", "unknown"),
                    "strategy_type": bot.get("strategy_type", "unknown"),
                    "trading_pair": bot.get("trading_pair", "unknown"),
                    "mode": "unknown",
                    "live_trading": False,
                    "testnet": False,
                    "status": bot.get("status", "unknown"),
                    "started_at": bot.get("started_at", ""),
                    "runtime_seconds": bot.get("runtime_seconds", 0),
                    "source": hummingbot_source,
                })

        return {
            "connected": len(local_records) > 0 or hummingbot_bots is not None,
            "source": "quantagent",
            "data": {"bots": bots},
            "error": None,
        }

    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": {"bots": []},
            "error": str(e),
        }


async def get_paper_bot_detail(paper_bot_id: str) -> Dict[str, Any]:
    """
    获取单个 Paper Bot 详情。

    Args:
        paper_bot_id: Paper Bot ID

    Returns:
        Paper Bot 详情响应
    """
    try:
        # 获取本地记录
        record = get_paper_bot_record(paper_bot_id)

        if record:
            runtime = 0
            if record.get("started_at"):
                try:
                    started = datetime.fromisoformat(record["started_at"].replace("Z", "+00:00"))
                    runtime = int((datetime.now().astimezone() - started).total_seconds())
                except Exception:
                    pass

            return {
                "connected": True,
                "source": "local",
                "data": {
                    "paper_bot_id": record["paper_bot_id"],
                    "bot_name": record["bot_name"],
                    "strategy_type": record["strategy_type"],
                    "trading_pair": record["trading_pair"],
                    "mode": "paper",
                    "live_trading": False,
                    "testnet": False,
                    "status": record["status"],
                    "started_at": record["started_at"],
                    "runtime_seconds": runtime,
                    "config": sanitize_data(record.get("config", {})),
                    "last_error": record.get("last_error"),
                    "hummingbot_status_raw": None,
                },
                "error": None,
            }

        # 如果本地没有，尝试从 Hummingbot API 获取
        try:
            status_result = await _call_hummingbot_api("GET", "/bot-orchestration/status")
            bots = status_result.get("data", [])

            for bot in bots:
                if f"hummingbot_{bot.get('name')}" == paper_bot_id:
                    return {
                        "connected": True,
                        "source": "hummingbot-api",
                        "data": {
                            "paper_bot_id": paper_bot_id,
                            "bot_name": bot.get("name", "unknown"),
                            "strategy_type": "unknown",
                            "trading_pair": "unknown",
                            "mode": "unknown",
                            "live_trading": False,
                            "testnet": False,
                            "status": bot.get("status", "unknown"),
                            "started_at": bot.get("started_at", ""),
                            "runtime_seconds": bot.get("runtime_seconds", 0),
                            "config": None,
                            "last_error": None,
                            "hummingbot_status_raw": sanitize_data(bot),
                        },
                        "error": None,
                    }
        except Exception:
            pass

        return {
            "connected": False,
            "source": "quantagent",
            "data": None,
            "error": f"Paper Bot '{paper_bot_id}' 不存在",
        }

    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": None,
            "error": str(e),
        }


async def get_paper_bot_orders(paper_bot_id: str) -> Dict[str, Any]:
    """
    获取 Paper Bot 模拟订单。

    注意：当前 Hummingbot API 不支持按 bot_id 精确过滤，
    返回全局订单并在响应中提示。

    Args:
        paper_bot_id: Paper Bot ID

    Returns:
        订单列表响应
    """
    try:
        # 尝试获取 Hummingbot API 订单
        orders = []
        source = None

        try:
            # 尝试活跃订单
            result = await _call_hummingbot_api("POST", "/trading/orders/active", json_data={})
            source = "orders_active"
            if result:
                orders = sanitize_data(result.get("data", []) or result)
        except Exception:
            pass

        # 如果没有活跃订单，尝试搜索
        if not orders:
            try:
                import time
                end_time = int(time.time() * 1000)
                start_time = end_time - 86400000  # 24小时内
                result = await _call_hummingbot_api(
                    "POST",
                    "/trading/orders/search",
                    json_data={"start_time": start_time, "end_time": end_time}
                )
                source = "orders_search"
                if result:
                    orders = sanitize_data(result.get("data", []) or result)
            except Exception:
                pass

        # 确保 orders 是列表
        if not isinstance(orders, list):
            orders = []

        return {
            "connected": True,
            "source": "hummingbot-api",
            "data": {
                "paper_bot_id": paper_bot_id,
                "orders": orders,
                "filter_note": (
                    "当前 Hummingbot API 版本暂不支持按 Paper Bot 精确过滤，"
                    "以下为全局订单数据。"
                ),
            },
            "error": None,
        }

    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "orders": [],
                "filter_note": "获取订单失败",
            },
            "error": str(e),
        }


async def get_paper_bot_positions(paper_bot_id: str) -> Dict[str, Any]:
    """
    获取 Paper Bot 模拟持仓。

    Args:
        paper_bot_id: Paper Bot ID

    Returns:
        持仓列表响应
    """
    try:
        positions = []

        try:
            result = await _call_hummingbot_api("POST", "/trading/positions", json_data={})
            if result:
                positions = sanitize_data(result.get("data", []) or result)
        except Exception:
            pass

        # 确保 positions 是列表
        if not isinstance(positions, list):
            positions = []

        return {
            "connected": True,
            "source": "hummingbot-api",
            "data": {
                "paper_bot_id": paper_bot_id,
                "positions": positions,
                "filter_note": (
                    "当前 Hummingbot API 版本暂不支持按 Paper Bot 精确过滤，"
                    "以下为全局持仓数据。"
                ),
            },
            "error": None,
        }

    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "positions": [],
                "filter_note": "获取持仓失败",
            },
            "error": str(e),
        }


async def get_paper_bot_portfolio(paper_bot_id: str) -> Dict[str, Any]:
    """
    获取 Paper Bot 模拟资产。

    Args:
        paper_bot_id: Paper Bot ID

    Returns:
        资产响应
    """
    try:
        portfolio = None

        try:
            result = await _call_hummingbot_api("POST", "/portfolio/state", json_data={})
            if result:
                portfolio = sanitize_data(result)
        except Exception:
            pass

        return {
            "connected": True,
            "source": "hummingbot-api",
            "data": {
                "paper_bot_id": paper_bot_id,
                "portfolio": portfolio,
                "filter_note": (
                    "当前 Hummingbot API 版本暂不支持按 Paper Bot 精确隔离资产，"
                    "以下为全局 Portfolio 数据。"
                ),
            },
            "error": None,
        }

    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "portfolio": None,
                "filter_note": "获取 Portfolio 失败",
            },
            "error": str(e),
        }


async def get_paper_bot_logs(paper_bot_id: str) -> Dict[str, Any]:
    """
    获取 Paper Bot 日志。

    Args:
        paper_bot_id: Paper Bot ID

    Returns:
        日志响应
    """
    try:
        # 尝试获取 Hummingbot 状态以获取容器信息
        container_name = None
        try:
            # 从 paper_bot_id 提取容器名
            if paper_bot_id.startswith("paper_"):
                container_name = f"hummingbot-{paper_bot_id.split('_')[1]}"
            else:
                container_name = paper_bot_id.replace("_", "-")
        except Exception:
            pass

        # 尝试获取容器日志
        logs_available = False
        logs = []
        logs_message = None

        if container_name:
            try:
                # 尝试 Docker logs API（如果 Hummingbot API 支持）
                result = await _call_hummingbot_api(
                    "GET",
                    f"/docker/containers/{container_name}/logs?stdout=true&stderr=true&tail=100"
                )
                logs_available = True
                raw_logs = result.get("logs", [])
                # 限制日志处理深度和数量
                if isinstance(raw_logs, list):
                    logs = [str(line)[:500] for line in raw_logs[:100]]  # 只取前100条，每条限制500字符
                else:
                    logs = [str(raw_logs)[:500]]
            except Exception:
                pass

        if not logs_available:
            logs_message = (
                "当前 Hummingbot API 版本暂未提供 Paper Bot 日志接口。"
                " 请通过 docker compose logs 查看容器日志。"
            )

        return {
            "connected": True,
            "source": "hummingbot-api",
            "data": {
                "paper_bot_id": paper_bot_id,
                "logs_available": logs_available,
                "lines": logs if isinstance(logs, list) else [],
                "message": logs_message,
            },
            "error": None,
        }

    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "logs_available": False,
                "lines": [],
                "message": f"获取日志失败: {str(e)}",
            },
            "error": str(e),
        }


# ── v1.2.4: 停止 Paper Bot ─────────────────────────────────────────────────

class PaperBotStopError(Exception):
    """停止 Paper Bot 时的校验或执行错误"""
    def __init__(self, message: str, code: str = "STOP_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


def _check_stop_sensitive_fields(data: Any) -> Optional[str]:
    """
    检查停止请求中是否包含敏感字段。

    Returns:
        错误信息，如果有敏感字段的话
    """
    if not data:
        return None

    if isinstance(data, dict):
        for key in data.keys():
            key_lower = key.lower()
            if any(sk in key_lower for sk in SENSITIVE_KEYS):
                return f"停止 Paper Bot 请求中不允许包含字段 '{key}'"
        for value in data.values():
            err = _check_stop_sensitive_fields(value)
            if err:
                return err
    elif isinstance(data, list):
        for item in data:
            err = _check_stop_sensitive_fields(item)
            if err:
                return err

    return None


def _log_paper_bot_stop(
    paper_bot_id: str,
    bot_name: str,
    previous_status: str,
    new_status: str,
    success: bool,
    error_message: Optional[str] = None,
    request_data: Optional[Dict[str, Any]] = None,
) -> None:
    """记录 Paper Bot 停止操作日志（不含敏感信息）"""
    try:
        log_entry = {
            "operation_type": "stop_paper_bot",
            "paper_bot_id": paper_bot_id,
            "bot_name": bot_name,
            "mode": "paper",
            "live_trading": False,
            "testnet": False,
            "previous_status": previous_status,
            "new_status": new_status,
            "success": success,
            "error_message": error_message,
            "has_sensitive_fields": _check_stop_sensitive_fields(request_data) is not None if request_data else False,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        logger.info(f"[PaperBot Stop] {json.dumps(log_entry, default=str)}")
    except Exception as e:
        logger.error(f"[PaperBot Stop] Failed to log: {e}")


async def stop_paper_bot(
    paper_bot_id: str,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    停止 Paper Bot。

    核心安全规则：
    1. 只允许停止 Paper Bot（mode=paper）
    2. 不允许停止 Testnet / Live Bot
    3. 不允许包含任何敏感字段
    4. 不伪造停止成功

    Args:
        paper_bot_id: Paper Bot ID
        raw_request_data: 原始请求体（用于敏感字段检查）

    Returns:
        停止结果
    """
    now = datetime.utcnow().isoformat() + "Z"

    # ── Step 1: 校验 confirm ───────────────────────────────────────────────
    confirm = raw_request_data.get("confirm") if raw_request_data else None
    if confirm is not True:
        return {
            "stopped": False,
            "source": "quantagent",
            "mode": "paper",
            "live_trading": False,
            "testnet": False,
            "data": None,
            "error": "缺少 confirm=true，必须明确确认才能停止 Paper Bot。",
            "timestamp": now,
        }

    # ── Step 2: 检查敏感字段 ───────────────────────────────────────────────
    sensitive_error = _check_stop_sensitive_fields(raw_request_data)
    if sensitive_error:
        _log_paper_bot_stop(
            paper_bot_id=paper_bot_id,
            bot_name="unknown",
            previous_status="unknown",
            new_status="unknown",
            success=False,
            error_message=sensitive_error,
            request_data=raw_request_data,
        )
        return {
            "stopped": False,
            "source": "quantagent",
            "mode": "paper",
            "live_trading": False,
            "testnet": False,
            "data": None,
            "error": sensitive_error,
            "timestamp": now,
        }

    # ── Step 3: 获取本地记录 ───────────────────────────────────────────────
    record = get_paper_bot_record(paper_bot_id)

    if not record:
        return {
            "stopped": False,
            "source": "quantagent",
            "mode": "paper",
            "live_trading": False,
            "testnet": False,
            "data": None,
            "error": f"Paper Bot '{paper_bot_id}' 不存在。",
            "timestamp": now,
        }

    bot_name = record.get("bot_name", "unknown")
    previous_status = record.get("status", "unknown")

    # ── Step 4: 安全校验 ───────────────────────────────────────────────────
    mode = record.get("mode", "paper")
    live_trading = record.get("live_trading", False)
    testnet = record.get("testnet", False)

    # 检查 mode
    if mode not in ("paper", None):
        _log_paper_bot_stop(
            paper_bot_id=paper_bot_id,
            bot_name=bot_name,
            previous_status=previous_status,
            new_status=previous_status,
            success=False,
            error_message=f"禁止停止 mode={mode} 的 Bot。只允许停止 Paper Bot。",
            request_data=raw_request_data,
        )
        return {
            "stopped": False,
            "source": "quantagent",
            "mode": mode,
            "live_trading": live_trading,
            "testnet": testnet,
            "data": None,
            "error": f"禁止停止 mode={mode} 的 Bot。只允许停止 Paper Bot。",
            "timestamp": now,
        }

    # 检查 live_trading
    if live_trading is True:
        _log_paper_bot_stop(
            paper_bot_id=paper_bot_id,
            bot_name=bot_name,
            previous_status=previous_status,
            new_status=previous_status,
            success=False,
            error_message="禁止停止 live_trading=true 的 Bot。",
            request_data=raw_request_data,
        )
        return {
            "stopped": False,
            "source": "quantagent",
            "mode": mode,
            "live_trading": live_trading,
            "testnet": testnet,
            "data": None,
            "error": "禁止停止 live_trading=true 的 Bot。",
            "timestamp": now,
        }

    # 检查 testnet
    if testnet is True:
        _log_paper_bot_stop(
            paper_bot_id=paper_bot_id,
            bot_name=bot_name,
            previous_status=previous_status,
            new_status=previous_status,
            success=False,
            error_message="禁止停止 testnet=true 的 Bot。",
            request_data=raw_request_data,
        )
        return {
            "stopped": False,
            "source": "quantagent",
            "mode": mode,
            "live_trading": live_trading,
            "testnet": testnet,
            "data": None,
            "error": "禁止停止 testnet=true 的 Bot。",
            "timestamp": now,
        }

    # ── Step 5: 如果已经停止 ───────────────────────────────────────────────
    if previous_status in ("stopped", "stopping", "error"):
        _log_paper_bot_stop(
            paper_bot_id=paper_bot_id,
            bot_name=bot_name,
            previous_status=previous_status,
            new_status="stopped",
            success=True,
            error_message=None,
            request_data=raw_request_data,
        )
        return {
            "stopped": True,
            "source": "quantagent",
            "mode": mode,
            "live_trading": live_trading,
            "testnet": testnet,
            "data": {
                "paper_bot_id": paper_bot_id,
                "bot_name": bot_name,
                "strategy_type": record.get("strategy_type", "unknown"),
                "trading_pair": record.get("trading_pair", "unknown"),
                "previous_status": previous_status,
                "status": "stopped",
                "stopped_at": now,
                "message": "该 Paper Bot 已处于停止状态。",
            },
            "error": None,
            "timestamp": now,
        }

    # ── Step 6: 更新状态为 stopping ───────────────────────────────────────
    update_paper_bot_status(paper_bot_id, "stopping")

    # ── Step 7: 调用 Hummingbot API 停止 ─────────────────────────────────
    hummingbot_response = None
    stop_success = False
    stop_error = None

    try:
        # 尝试调用 Hummingbot API stop-bot 接口
        # POST /bot-orchestration/stop-bot
        # Body: {"bot_name": "...", "skip_order_cancellation": true}
        stop_payload = {
            "bot_name": record.get("bot_name", paper_bot_id),
            "skip_order_cancellation": True,  # 不撤单
            "async_backend": False,
        }
        hummingbot_response = await _call_hummingbot_api(
            "POST",
            "/bot-orchestration/stop-bot",
            json_data=stop_payload,
        )
        stop_success = True
        stop_error = None
    except Exception as e:
        stop_success = False
        stop_error = str(e)
        # 如果 stop-bot 接口不可用，尝试 docker stop-container
        if "404" in stop_error or "Not Found" in stop_error:
            try:
                container_name = f"hummingbot-{paper_bot_id}"
                hummingbot_response = await _call_hummingbot_api(
                    "POST",
                    f"/docker/stop-container/{container_name}",
                )
                stop_success = True
                stop_error = None
            except Exception as e2:
                stop_error = (
                    "当前 Hummingbot API 版本未提供可用的 Paper Bot 停止接口。"
                    " 请检查 Swagger /docs 或通过 docker compose stop 停止容器。"
                    f" stop-bot 错误: {str(e)}"
                )
        else:
            stop_error = f"停止 Paper Bot 失败: {stop_error}"

    # ── Step 8: 更新本地状态 ──────────────────────────────────────────────
    if stop_success:
        update_paper_bot_status(paper_bot_id, "stopped")
        new_status = "stopped"
    else:
        update_paper_bot_status(paper_bot_id, previous_status)
        new_status = previous_status

    # ── Step 9: 记录日志 ──────────────────────────────────────────────────
    _log_paper_bot_stop(
        paper_bot_id=paper_bot_id,
        bot_name=bot_name,
        previous_status=previous_status,
        new_status=new_status,
        success=stop_success,
        error_message=stop_error,
        request_data=raw_request_data,
    )

    # ── Step 10: 返回结果 ─────────────────────────────────────────────────
    return {
        "stopped": stop_success,
        "source": "hummingbot-api" if stop_success else ("hummingbot-api" if hummingbot_response else "quantagent"),
        "mode": mode,
        "live_trading": live_trading,
        "testnet": testnet,
        "data": {
            "paper_bot_id": paper_bot_id,
            "bot_name": bot_name,
            "strategy_type": record.get("strategy_type", "unknown"),
            "trading_pair": record.get("trading_pair", "unknown"),
            "previous_status": previous_status,
            "status": new_status,
            "stopped_at": now if stop_success else None,
            "hummingbot_response": sanitize_data(hummingbot_response) if hummingbot_response else None,
        } if stop_success else None,
        "error": stop_error,
        "timestamp": now,
    }
