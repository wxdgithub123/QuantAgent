"""
Hummingbot Paper Bot Service

v1.2.x 核心设计：local_status 与 remote_status 分离
- local_status: QuantAgent 本地记录状态
- remote_status: Hummingbot 远端检测状态（通过 active_bots 对账得出）
- GET /paper-bots: 读取本地记录 + 调用 Hummingbot API 对账，不显示未确认的 running
"""

import json
import logging
import time
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

logger = logging.getLogger(__name__)


# ── 敏感字段黑名单 ──────────────────────────────────────────────────────────────

SENSITIVE_FIELD_PATTERNS = [
    "api_key", "apikey", "apiSecret", "api_secret", "secret",
    "private_key", "privateKey", "exchange_secret", "exchangeSecret",
    "password", "passphrase", "token", "access_token", "refresh_token",
    "wallet_private_key", "wallet_privatekey", "mnemonic", "seed_phrase", "seedphrase",
    "real_trading", "live_trading", "testnet",
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
    live_trading_value = flat_data.get("live_trading")
    if live_trading_value is True or str(live_trading_value).lower() == "true":
        return "检测到 live_trading=true。仅支持 Paper Bot，不支持真实交易。"
    testnet_value = flat_data.get("testnet")
    if testnet_value is True or str(testnet_value).lower() == "true":
        return "检测到 testnet=true。仅支持 Paper Bot。"
    return None


def _validate_strategy_params(request: PaperBotPreviewRequest) -> None:
    if request.strategy_type.value == "grid":
        if request.grid_spacing_pct is None or request.grid_spacing_pct <= 0:
            raise HummingbotPaperBotValidationError(
                "grid 策略必须提供有效的 grid_spacing_pct（> 0）"
            )
        if request.grid_levels < 2 or request.grid_levels > 200:
            raise HummingbotPaperBotValidationError(
                "grid_levels 必须在 2-200 之间"
            )


def _validate_order_amount(request: PaperBotPreviewRequest) -> None:
    if request.order_amount > request.paper_initial_balance:
        raise HummingbotPaperBotValidationError(
            f"单笔订单金额 ({request.order_amount}) 不能大于初始资金 ({request.paper_initial_balance})"
        )


def _build_config_preview(request: PaperBotPreviewRequest) -> Dict[str, Any]:
    risk_config = {
        "stop_loss_pct": request.stop_loss_pct or 0,
        "take_profit_pct": request.take_profit_pct or 0,
        "max_runtime_minutes": request.max_runtime_minutes,
    }
    strategy_params: Dict[str, Any] = {}
    if request.strategy_type.value == "position_executor":
        if request.spread_pct is not None:
            strategy_params["spread_pct"] = request.spread_pct
    elif request.strategy_type.value == "grid":
        strategy_params["grid_spacing_pct"] = request.grid_spacing_pct
        strategy_params["grid_levels"] = request.grid_levels or 20

    notes = [
        "当前配置仅用于 Paper Bot 预览。",
        "不会执行真实交易。",
        "不会使用真实交易所 API Key。",
        f"策略类型: {request.strategy_type.value}",
        f"交易对: {request.trading_pair}",
    ]
    return {
        "bot_name": request.bot_name,
        "mode": "paper",
        "live_trading": False,
        "testnet": False,
        "uses_real_exchange_account": False,
        "requires_api_key": False,
        "strategy_type": request.strategy_type.value,
        "trading_pair": request.trading_pair,
        "paper_initial_balance": request.paper_initial_balance,
        "order_amount": request.order_amount,
        "risk": risk_config,
        "strategy_params": strategy_params,
        "notes": notes,
    }


def sanitize_data(data: Any, depth: int = 0) -> Any:
    if data is None:
        return None
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
        if k not in SENSITIVE_KEYS and k not in ["password", "api_key", "secret"]
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
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }, default=str))


# ── Hummingbot API 调用 ────────────────────────────────────────────────────────

async def _call_hummingbot_api(
    method: str,
    path: str,
    json_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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
            method=method, url=url, json=json_data, auth=auth
        )
        if response.status_code == 401:
            raise Exception("Hummingbot API 认证失败")
        elif not response.is_success:
            raise Exception(
                f"Hummingbot API 请求失败: HTTP {response.status_code} - {response.text[:200]}"
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
) -> None:
    """创建本地记录，初始状态为 submitted（已提交，待对账）"""
    now = datetime.utcnow().isoformat() + "Z"
    _paper_bot_records[paper_bot_id] = {
        "paper_bot_id": paper_bot_id,
        "bot_name": bot_name,
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
    }


def update_paper_bot_fields(
    paper_bot_id: str,
    **fields,
) -> None:
    """更新 Paper Bot 记录字段"""
    if paper_bot_id in _paper_bot_records:
        _paper_bot_records[paper_bot_id].update(fields)


def get_paper_bot_records() -> Dict[str, Dict[str, Any]]:
    return _paper_bot_records


def get_paper_bot_record(paper_bot_id: str) -> Optional[Dict[str, Any]]:
    return _paper_bot_records.get(paper_bot_id)


# ── v1.2.1: 配置预览 ──────────────────────────────────────────────────────────

async def generate_paper_bot_preview(
    request: PaperBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> PaperBotPreviewResponse:
    try:
        if raw_request_data:
            sensitive_error = _check_sensitive_fields(raw_request_data)
            if sensitive_error:
                return PaperBotPreviewResponse(valid=False, error=sensitive_error)

            mode_error = _check_dangerous_modes(raw_request_data)
            if mode_error:
                return PaperBotPreviewResponse(valid=False, error=mode_error)

        _validate_strategy_params(request)
        _validate_order_amount(request)
        config_preview_dict = _build_config_preview(request)

        preview_data = PaperBotPreviewData(
            config_preview=ConfigPreview(**config_preview_dict),
            warnings=[
                "当前仅生成配置预览，尚未调用 Hummingbot API 启动 Bot。"
            ],
        )
        return PaperBotPreviewResponse(valid=True, data=preview_data)

    except HummingbotPaperBotValidationError as e:
        return PaperBotPreviewResponse(valid=False, error=e.message)
    except Exception as e:
        return PaperBotPreviewResponse(
            valid=False,
            error=f"生成预览时发生未知错误: {str(e)}",
        )


# ── v1.2.2: 启动 Paper Bot（已修复：不伪造 started=true）───────────────────────

async def start_paper_bot(
    request: PaperBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> PaperBotStartResponse:
    """启动 Paper Bot

    关键设计：
    - submitted=True: 已提交到 Hummingbot API（但不一定成功）
    - remote_confirmed=False: 需要通过 GET /paper-bots 对账后才会显示 remote_status=running
    - local_status=submitted: 不是 running，只有对账后才能升级为 running
    """
    try:
        if raw_request_data:
            sensitive_error = _check_sensitive_fields(raw_request_data)
            if sensitive_error:
                return PaperBotStartResponse(submitted=False, remote_confirmed=False, error=sensitive_error)

            mode_error = _check_dangerous_modes(raw_request_data)
            if mode_error:
                return PaperBotStartResponse(submitted=False, remote_confirmed=False, error=mode_error)

        _validate_strategy_params(request)
        _validate_order_amount(request)

        config_preview_dict = _build_config_preview(request)
        paper_bot_id = f"paper_{request.bot_name}_{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow().isoformat() + "Z"

        # 先创建本地记录，状态为 submitted
        record_paper_bot(
            paper_bot_id=paper_bot_id,
            bot_name=request.bot_name,
            strategy_type=request.strategy_type.value,
            trading_pair=request.trading_pair,
            config=config_preview_dict,
        )

        # 尝试调用 Hummingbot API
        hummingbot_response = None
        api_submitted = False
        api_confirmed = False
        api_error: Optional[str] = None

        try:
            # 检测 API 是否可用
            await _call_hummingbot_api("GET", "/")
        except Exception as e:
            api_error = f"Hummingbot API 不可用: {str(e)}"
            logger.warning(f"Hummingbot API not available: {e}")
            return PaperBotStartResponse(
                submitted=False,
                remote_confirmed=False,
                error=(
                    f"无法连接到 Hummingbot API。{api_error}。"
                    " 请检查 Hummingbot API 是否启动。"
                ),
            )

        try:
            # 调用部署接口
            start_payload = {
                "instance_name": paper_bot_id,
                "credentials_profile": "paper_account",
                "controllers_config": [],
                "headless": True,
            }
            hummingbot_response = await _call_hummingbot_api(
                "POST",
                "/bot-orchestration/deploy-v2-controllers",
                json_data=start_payload,
            )
            api_submitted = True
            # 即使 API 返回 200/201，也需要下次 GET 对账才能确认 remote_confirmed
            # 因为 Bot 可能还在启动中
        except Exception as e:
            api_submitted = False
            api_confirmed = False
            api_error = f"Hummingbot API 调用失败: {str(e)}"
            logger.warning(f"Failed to start Paper Bot via Hummingbot API: {e}")

        # 更新本地记录
        if api_submitted:
            update_paper_bot_fields(
                paper_bot_id,
                local_status="submitted",
                hummingbot_status_raw=sanitize_data(hummingbot_response),
                last_error=None,
            )
        else:
            update_paper_bot_fields(
                paper_bot_id,
                local_status="submitted",
                last_error=api_error,
            )

        start_data = PaperBotStartData(
            paper_bot_id=paper_bot_id,
            bot_name=request.bot_name,
            strategy_type=request.strategy_type.value,
            trading_pair=request.trading_pair,
            local_status="submitted",
            remote_confirmed=False,
            hummingbot_bot_id=hummingbot_response.get("instance_id") if hummingbot_response else None,
            started_at=now,
            config=config_preview_dict,
            hummingbot_response=sanitize_data(hummingbot_response),
        )

        if api_submitted:
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=True,
                config=config_preview_dict,
            )
            return PaperBotStartResponse(
                submitted=True,
                remote_confirmed=False,
                data=start_data,
            )
        else:
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=False,
                error_message=api_error,
                config=config_preview_dict,
            )
            return PaperBotStartResponse(
                submitted=False,
                remote_confirmed=False,
                error=api_error,
            )

    except HummingbotPaperBotValidationError as e:
        return PaperBotStartResponse(submitted=False, remote_confirmed=False, error=e.message)
    except Exception as e:
        return PaperBotStartResponse(
            submitted=False,
            remote_confirmed=False,
            error=f"启动 Paper Bot 时发生未知错误: {str(e)}",
        )


# ── v1.2.3: 查询 Paper Bot 列表（对账逻辑）─────────────────────────────────────

async def _fetch_hummingbot_active_bots() -> tuple[List[Dict], str]:
    """
    从 Hummingbot API 获取 active bots。
    尝试多个接口，返回 (bots, matched_by)
    """
    # 尝试 /bot-orchestration/status
    try:
        result = await _call_hummingbot_api("GET", "/bot-orchestration/status")
        bots = result.get("data", []) or []
        if isinstance(bots, dict):
            # 可能是 {active_bots: [...], disconnected_bots: [...]}
            active = bots.get("active_bots", [])
            disconnected = bots.get("disconnected_bots", [])
            bots = list(active) + list(disconnected)
        if isinstance(bots, list):
            return sanitize_data(bots), "bot_api"
    except Exception as e:
        logger.warning(f"Failed to fetch from /bot-orchestration/status: {e}")

    # 尝试 /bots
    try:
        result = await _call_hummingbot_api("GET", "/bots/")
        bots = result.get("data", []) or []
        if isinstance(bots, list):
            return sanitize_data(bots), "active_bots"
    except Exception as e:
        logger.warning(f"Failed to fetch from /bots/: {e}")

    return [], "none"


async def get_paper_bots_list() -> Dict[str, Any]:
    """
    获取 Paper Bot 列表，并对账 Hummingbot API 远端状态。

    流程：
    1. 读取所有本地记录的 Paper Bot
    2. 调用 Hummingbot API 获取 active_bots
    3. 尝试用 paper_bot_id、bot_name 匹配
    4. 匹配到的 Bot: remote_status=running, matched_remote_bot=True
    5. 匹配不到的 Bot: remote_status=not_detected, matched_remote_bot=False
    """
    now = datetime.utcnow().isoformat() + "Z"

    # Step 1: 读取本地记录
    local_records = get_paper_bot_records()

    # Step 2: 获取远端 active bots
    remote_bots, matched_by = await _fetch_hummingbot_active_bots()

    # Step 3: 构建远端 Bot ID → Bot 映射
    remote_bot_map: Dict[str, Dict] = {}
    for bot in remote_bots:
        name = bot.get("name") or bot.get("instance_name") or bot.get("bot_name") or ""
        if name:
            remote_bot_map[str(name).lower()] = bot

    # Step 4: 对账
    bots = []
    for paper_bot_id, record in local_records.items():
        bot_name = record.get("bot_name", "").lower()

        # 尝试匹配远端 Bot
        matched = False
        matched_hb_bot: Optional[Dict] = None
        hummingbot_bot_id: Optional[str] = None

        # 匹配方式1: paper_bot_id 匹配 instance_name
        if paper_bot_id.lower() in remote_bot_map:
            matched = True
            matched_hb_bot = remote_bot_map[paper_bot_id.lower()]
        # 匹配方式2: bot_name 匹配 name
        elif bot_name in remote_bot_map:
            matched = True
            matched_hb_bot = remote_bot_map[bot_name]
        # 匹配方式3: 模糊匹配（远端 name 包含本地 bot_name）
        else:
            for remote_name, remote_bot in remote_bot_map.items():
                if bot_name in remote_name or remote_name in bot_name:
                    matched = True
                    matched_hb_bot = remote_bot
                    break

        if matched and matched_hb_bot:
            hummingbot_bot_id = (
                matched_hb_bot.get("name")
                or matched_hb_bot.get("instance_name")
                or matched_hb_bot.get("bot_name")
                or None
            )
            remote_status = "running"
            local_status = "running"
        else:
            remote_status = "not_detected"
            # 本地状态不变（submitted/starting/stopped/error）
            local_status = record.get("local_status", "submitted")

        # 更新本地记录的远端状态（供详情使用）
        update_paper_bot_fields(
            paper_bot_id,
            remote_status=remote_status,
            matched_remote_bot=matched,
            matched_by="none" if not matched else matched_by,
            hummingbot_bot_id=hummingbot_bot_id,
            last_remote_check_at=now,
        )

        # 计算运行时长
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
            "local_status": local_status,
            "remote_status": remote_status,
            "matched_remote_bot": matched,
            "matched_by": "none" if not matched else matched_by,
            "hummingbot_bot_id": hummingbot_bot_id,
            "started_at": started_at,
            "runtime_seconds": runtime,
            "last_error": record.get("last_error"),
        })

    # 按启动时间倒序
    bots.sort(key=lambda b: b.get("started_at") or "", reverse=True)

    return {
        "connected": len(remote_bots) > 0,
        "source": "quantagent",
        "data": {
            "bots": bots,
            "reconciliation": {
                "remote_bots_found": len(remote_bots),
                "matched_by": matched_by,
                "last_check_at": now,
            },
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 详情 ───────────────────────────────────────────────

async def get_paper_bot_detail(paper_bot_id: str) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat() + "Z"

    # Step 1: 获取本地记录
    record = get_paper_bot_record(paper_bot_id)

    if not record:
        return {
            "connected": False,
            "source": "quantagent",
            "data": None,
            "error": f"Paper Bot '{paper_bot_id}' 不存在",
        }

    # Step 2: 检查远端状态
    remote_bots, matched_by = await _fetch_hummingbot_active_bots()
    remote_bot_map = {
        str(b.get("name") or b.get("instance_name") or "").lower(): b
        for b in remote_bots
    }

    bot_name = record.get("bot_name", "").lower()
    matched = paper_bot_id.lower() in remote_bot_map or bot_name in remote_bot_map

    if matched:
        matched_hb_bot = remote_bot_map.get(paper_bot_id.lower()) or remote_bot_map.get(bot_name)
        remote_status = "running"
        local_status = "running"
        hummingbot_bot_id = (
            matched_hb_bot.get("name")
            or matched_hb_bot.get("instance_name")
            or None
        )
        hummingbot_status_raw = matched_hb_bot
    else:
        remote_status = "not_detected"
        local_status = record.get("local_status", "submitted")
        hummingbot_bot_id = None
        hummingbot_status_raw = None

    update_paper_bot_fields(
        paper_bot_id,
        remote_status=remote_status,
        matched_remote_bot=matched,
        matched_by="none" if not matched else matched_by,
        hummingbot_bot_id=hummingbot_bot_id,
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
            "local_status": local_status,
            "remote_status": remote_status,
            "matched_remote_bot": matched,
            "matched_by": "none" if not matched else matched_by,
            "hummingbot_bot_id": hummingbot_bot_id,
            "last_remote_check_at": now,
            "started_at": started_at,
            "runtime_seconds": runtime,
            "config": sanitize_data(record.get("config", {})),
            "last_error": record.get("last_error"),
            "hummingbot_status_raw": sanitize_data(hummingbot_status_raw),
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 订单 ───────────────────────────────────────────────

async def get_paper_bot_orders(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    remote_status = "not_detected"
    if record:
        remote_status = record.get("remote_status", "not_detected")

    if remote_status != "running":
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

    # remote_status == running，尝试获取订单
    try:
        result = await _call_hummingbot_api("POST", "/trading/orders/active", json_data={})
        orders = sanitize_data(result.get("data", []) or result)
        if not isinstance(orders, list):
            orders = []
    except Exception:
        orders = []

    if not orders:
        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - 86400000
            result = await _call_hummingbot_api(
                "POST",
                "/trading/orders/search",
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
            "filter_note": "以下为全局订单数据，Hummingbot API 暂不支持按 Bot 精确过滤。" if orders else "暂无订单数据。",
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 持仓 ───────────────────────────────────────────────

async def get_paper_bot_positions(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    remote_status = "not_detected"
    if record:
        remote_status = record.get("remote_status", "not_detected")

    if remote_status != "running":
        return {
            "connected": True,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "positions": [],
                "filter_note": (
                    "当前 Paper Bot 尚未被 Hummingbot 远端确认运行（remote_status=not_detected），"
                    "因此暂无模拟持仓。需先通过 GET /paper-bots 对账确认 Bot 真正运行后，才能获取持仓数据。"
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
            "filter_note": "以下为全局持仓数据，Hummingbot API 暂不支持按 Bot 精确隔离。" if positions else "暂无持仓数据。",
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 资产 ───────────────────────────────────────────────

async def get_paper_bot_portfolio(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    remote_status = "not_detected"
    if record:
        remote_status = record.get("remote_status", "not_detected")

    if remote_status != "running":
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
            "filter_note": "Hummingbot API 暂不支持按 Bot 精确隔离 Portfolio，数据可能包含其他 Bot。" if portfolio else "暂无 Portfolio 数据。",
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 日志 ───────────────────────────────────────────────

async def get_paper_bot_logs(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    remote_status = "not_detected"
    if record:
        remote_status = record.get("remote_status", "not_detected")

    logs_message = None
    if remote_status != "running":
        logs_message = (
            "当前 Paper Bot 尚未被 Hummingbot 远端确认运行（remote_status=not_detected），"
            "因此暂无运行日志。需先通过 GET /paper-bots 对账确认 Bot 真正运行后，才能获取日志。"
        )

    container_name = None
    if paper_bot_id.startswith("paper_"):
        parts = paper_bot_id.split("_")
        if len(parts) >= 2:
            container_name = f"hummingbot-{parts[1]}"

    logs_available = False
    logs: List[str] = []

    if remote_status == "running" and container_name:
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

    if not logs_available and remote_status == "running":
        logs_message = (
            "当前 Hummingbot API 版本暂未提供 Bot 容器日志接口。"
            " 请通过 docker compose logs 查看容器日志。"
        )

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


# ── v1.2.4: 停止 Paper Bot ─────────────────────────────────────────────────────

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
    try:
        logger.info(json.dumps({
            "operation_type": "stop_paper_bot",
            "paper_bot_id": paper_bot_id,
            "bot_name": bot_name,
            "previous_local_status": previous_status,
            "new_local_status": new_status,
            "success": success,
            "error_message": error_message,
            "has_sensitive_fields": _check_stop_sensitive_fields(request_data) is not None if request_data else False,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }, default=str))
    except Exception as e:
        logger.error(f"[PaperBot Stop] Failed to log: {e}")


async def stop_paper_bot(
    paper_bot_id: str,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat() + "Z"

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

    sensitive_error = _check_stop_sensitive_fields(raw_request_data)
    if sensitive_error:
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
    previous_local_status = record.get("local_status", "unknown")

    # 安全校验
    mode = record.get("mode", "paper")
    live_trading = record.get("live_trading", False)
    testnet = record.get("testnet", False)

    if mode not in ("paper", None):
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
    if live_trading is True:
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
    if testnet is True:
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

    # 已停止的 Bot 再次停止返回成功
    if previous_local_status in ("stopped",):
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
                "local_status": "stopped",
                "stopped_at": now,
                "message": "该 Paper Bot 已处于停止状态。",
            },
            "error": None,
            "timestamp": now,
        }

    # 更新本地状态为 stopping
    update_paper_bot_fields(paper_bot_id, local_status="stopping")

    # 尝试调用 Hummingbot API 停止
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
            "POST",
            "/bot-orchestration/stop-bot",
            json_data=stop_payload,
        )
        stop_success = True
    except Exception as e:
        stop_error = str(e)
        if "404" in stop_error or "Not Found" in stop_error:
            try:
                container_name = f"hummingbot-{paper_bot_id.split('_')[1] if '_' in paper_bot_id else paper_bot_id}"
                hummingbot_response = await _call_hummingbot_api(
                    "POST",
                    f"/docker/stop-container/{container_name}",
                )
                stop_success = True
            except Exception as e2:
                stop_error = (
                    f"当前 Hummingbot API 版本未提供可用的 Paper Bot 停止接口。"
                    f" stop-bot: {str(e)}, docker: {str(e2)}"
                )
        else:
            stop_error = f"停止 Paper Bot 失败: {stop_error}"

    new_local_status = "stopped" if stop_success else previous_local_status
    update_paper_bot_fields(
        paper_bot_id,
        local_status=new_local_status,
        remote_status="not_detected",
        matched_remote_bot=False,
        matched_by="none",
    )

    _log_paper_bot_stop(
        paper_bot_id=paper_bot_id,
        bot_name=bot_name,
        previous_status=previous_local_status,
        new_status=new_local_status,
        success=stop_success,
        error_message=stop_error,
        request_data=raw_request_data,
    )

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
