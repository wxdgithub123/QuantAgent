"""
Hummingbot Paper Bot Service

v1.2.x: 本地状态与远端状态分离，完整 preflight 检查

核心设计：
1. start_paper_bot 在调用 API 前进行 preflight 检查
2. 动态创建 controller config（通过 /controllers/configs/ API）
3. 调用 deploy-v2-controllers 后立即验证 active_bots
4. 只有 active_bots 包含该 Bot 才设置 remote_started=true
5. API 返回 200 但 active_bots 为空 → start_failed（Docker 可能不可用）
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
    for field in ["live_trading", "testnet"]:
        val = flat_data.get(field)
        if val is True or str(val).lower() == "true":
            return f"检测到 {field}=true。仅支持 Paper Bot。"
    return None


def _validate_strategy_params(request: PaperBotPreviewRequest) -> None:
    if request.strategy_type.value == "grid":
        if not request.grid_spacing_pct or request.grid_spacing_pct <= 0:
            raise HummingbotPaperBotValidationError("grid 策略必须提供有效的 grid_spacing_pct（> 0）")
        if request.grid_levels < 2 or request.grid_levels > 200:
            raise HummingbotPaperBotValidationError("grid_levels 必须在 2-200 之间")


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
        "notes": [
            "当前配置仅用于 Paper Bot 预览。",
            "不会执行真实交易。",
            "不会使用真实交易所 API Key。",
            f"策略类型: {request.strategy_type.value}",
            f"交易对: {request.trading_pair}",
        ],
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
        "timestamp": datetime.utcnow().isoformat() + "Z",
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
) -> None:
    """创建本地记录，初始状态为 submitted"""
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


def update_paper_bot_fields(paper_bot_id: str, **fields) -> None:
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
            if err := _check_sensitive_fields(raw_request_data):
                return PaperBotPreviewResponse(valid=False, error=err)
            if err := _check_dangerous_modes(raw_request_data):
                return PaperBotPreviewResponse(valid=False, error=err)
        _validate_strategy_params(request)
        _validate_order_amount(request)
        config_preview_dict = _build_config_preview(request)
        preview_data = PaperBotPreviewData(
            config_preview=ConfigPreview(**config_preview_dict),
            warnings=["当前仅生成配置预览，尚未调用 Hummingbot API 启动 Bot。"],
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
        if not result.paper_account_available:
            result.preflight_errors.append(
                f"Hummingbot 中未找到 paper_account。可用账户: {result.accounts}。"
                " 请在 Hummingbot 中创建 paper_account。"
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

    # 综合判断
    result.preflight_passed = (
        result.api_online
        and result.paper_account_available
        and result.deploy_callable
        and len(result.preflight_errors) == 0
    )
    return result


async def _create_controller_config(
    config_name: str,
    request: PaperBotPreviewRequest,
) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    通过 /controllers/configs/ API 创建 controller config。

    根据 strategy_type 映射到 Hummingbot 支持的 controller：
    - grid → generic/grid_strike
    - position_executor → generic/pmm

    返回 (success, error_message, created_config)
    """
    # 映射策略到 controller
    strategy = request.strategy_type.value
    trading_pair = request.trading_pair.upper().replace("-", "-")

    # grid 策略使用 grid_strike controller
    if strategy == "grid":
        controller_type = "generic"
        controller_name = "grid_strike"
        # BTC-USDT → BTC-USDT (binance_perpetual needs uppercase)
        connector_name = _get_connector_for_pair(trading_pair)
        config_payload: Dict[str, Any] = {
            "id": config_name,
            "controller_type": controller_type,
            "controller_name": controller_name,
            "connector_name": connector_name,
            "trading_pair": trading_pair,
            "total_amount_quote": request.paper_initial_balance,
            "min_spread_between_orders": request.grid_spacing_pct / 100.0 if request.grid_spacing_pct else 0.005,
            "min_order_amount_quote": request.order_amount,
            "max_open_orders": request.grid_levels or 20,
            "side": "BUY",
            "start_price": _estimate_start_price(trading_pair),
            "end_price": _estimate_end_price(trading_pair, request.grid_spacing_pct or 0.5),
            "limit_price": _estimate_start_price(trading_pair),
            "leverage": 20,
            "position_mode": "HEDGE",
            "side": 1,
        }

    # position_executor 使用 pmm controller
    elif strategy == "position_executor":
        controller_type = "generic"
        controller_name = "pmm"
        connector_name = _get_connector_for_pair(trading_pair)
        config_payload = {
            "id": config_name,
            "controller_type": controller_type,
            "controller_name": controller_name,
            "connector_name": connector_name,
            "trading_pair": trading_pair,
            "total_amount_quote": request.paper_initial_balance,
            "min_order_amount_quote": request.order_amount,
            "leverage": 20,
            "position_mode": "HEDGE",
        }
        if request.spread_pct:
            config_payload["bid_spread"] = request.spread_pct
            config_payload["ask_spread"] = request.spread_pct

    else:
        return False, f"不支持的策略类型: {strategy}", None

    try:
        resp = await _call_hummingbot_api(
            "POST",
            f"/controllers/configs/{config_name}",
            json_data=config_payload,
            timeout=20.0,
        )
        return True, None, config_payload
    except Exception as e:
        return False, f"创建 controller config 失败: {str(e)}", None


def _get_connector_for_pair(trading_pair: str) -> str:
    """根据交易对返回 connector 名称"""
    pair_upper = trading_pair.upper()
    if "USDT" in pair_upper or "BTC" in pair_upper or "ETH" in pair_upper:
        return "binance_perpetual"
    return "binance_perpetual"


def _estimate_start_price(trading_pair: str) -> float:
    """根据交易对估算起始价格"""
    pair_upper = trading_pair.upper()
    if "BTC" in pair_upper:
        return 65000.0
    elif "ETH" in pair_upper:
        return 3500.0
    elif "SOL" in pair_upper:
        return 150.0
    elif "BNB" in pair_upper:
        return 600.0
    elif "DOGE" in pair_upper:
        return 0.15
    return 100.0


def _estimate_end_price(trading_pair: str, grid_spacing_pct: float) -> float:
    """根据交易对和网格间距估算结束价格"""
    start = _estimate_start_price(trading_pair)
    return start * (1 + grid_spacing_pct / 100.0 * 10)


async def _verify_bot_in_active_list(
    instance_name: str,
    bot_name: str,
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    验证 Bot 是否在 Hummingbot active_bots 列表中。
    返回 (found, matching_bot_data)
    """
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
                inst_lower = instance_name.lower()
                bot_lower = bot_name.lower()
                if inst_lower in name or bot_lower in name or name in inst_lower:
                    matched_bot = sanitize_data(bot)

        # 新格式: data 是 dict，key 是 instance_name
        if not matched_bot and isinstance(data, dict):
            inst_lower = instance_name.lower()
            bot_lower = bot_name.lower()
            for key, bot_info in data.items():
                key_lower = key.lower()
                if inst_lower in key_lower or bot_lower in key_lower or key_lower in inst_lower:
                    matched_bot = sanitize_data(bot_info)

        if matched_bot:
            return True, matched_bot
        return False, None

    except Exception:
        return False, None


async def start_paper_bot(
    request: PaperBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> PaperBotStartResponse:
    """
    启动 Paper Bot（完整实现）

    完整流程：
    1. 安全校验（敏感字段、危险模式）
    2. Preflight 检查（API 在线、credentials、controller configs、deploy 接口）
    3. 如果 preflight 失败 → start_failed，清晰错误
    4. 动态创建 controller config
    5. 调用 deploy-v2-controllers
    6. 立即验证 active_bots
    7. 只有 active_bots 包含该 Bot → remote_started=true
    8. API 返回 200 但 active_bots 为空 → remote_started=false，Docker 可能不可用
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

        _validate_strategy_params(request)
        _validate_order_amount(request)

        config_preview_dict = _build_config_preview(request)
        paper_bot_id = f"paper_{request.bot_name}_{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow().isoformat() + "Z"

        # ── Step 2: Preflight 检查 ────────────────────────────────────────
        preflight = await _run_preflight_checks()

        if not preflight.preflight_passed:
            err_summary = preflight.error_summary()
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=False,
                error_message=err_summary,
                config=config_preview_dict,
            )
            return PaperBotStartResponse(
                local_record_created=False,
                remote_started=False,
                remote_confirmed=False,
                error=err_summary,
            )

        # ── Step 3: 创建 controller config ──────────────────────────────────
        controller_config_name = f"paper_{request.bot_name}_{uuid.uuid4().hex[:8]}"
        config_ok, config_err, _ = await _create_controller_config(
            config_name=controller_config_name,
            request=request,
        )

        if not config_ok:
            err_msg = f"无法创建 controller config: {config_err}"
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=False,
                error_message=err_msg,
                config=config_preview_dict,
            )
            return PaperBotStartResponse(
                local_record_created=False,
                remote_started=False,
                remote_confirmed=False,
                error=err_msg,
            )

        # ── Step 4: 调用 deploy-v2-controllers ────────────────────────────
        deploy_payload = {
            "instance_name": paper_bot_id,
            "credentials_profile": "paper_account",
            "controllers_config": [controller_config_name],
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
            deploy_call_ok = False
            deploy_call_err = str(e)
            logger.warning(f"deploy-v2-controllers 调用失败: {e}")

        if not deploy_call_ok:
            # 创建本地记录，状态为 start_failed
            record_paper_bot(
                paper_bot_id=paper_bot_id,
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                config=config_preview_dict,
            )
            update_paper_bot_fields(
                paper_bot_id,
                local_status="start_failed",
                last_error=deploy_call_err,
            )
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=False,
                error_message=f"deploy-v2-controllers 调用失败: {deploy_call_err}",
                config=config_preview_dict,
            )
            return PaperBotStartResponse(
                local_record_created=True,
                remote_started=False,
                remote_confirmed=False,
                data=PaperBotStartData(
                    paper_bot_id=paper_bot_id,
                    bot_name=request.bot_name,
                    strategy_type=request.strategy_type.value,
                    trading_pair=request.trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                    config=config_preview_dict,
                    hummingbot_response=sanitize_data(deploy_resp),
                ),
                error=f"调用 deploy-v2-controllers 失败: {deploy_call_err}",
            )

        # ── Step 5: 验证 active_bots ─────────────────────────────────────
        # deploy 返回 200，但必须验证 Bot 是否真正在 active 列表中
        found, matched_bot = await _verify_bot_in_active_list(paper_bot_id, request.bot_name)

        if found and matched_bot:
            # Bot 真正在运行
            record_paper_bot(
                paper_bot_id=paper_bot_id,
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                config=config_preview_dict,
            )
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
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=True,
                config=config_preview_dict,
            )
            return PaperBotStartResponse(
                local_record_created=True,
                remote_started=True,
                remote_confirmed=True,
                data=PaperBotStartData(
                    paper_bot_id=paper_bot_id,
                    bot_name=request.bot_name,
                    strategy_type=request.strategy_type.value,
                    trading_pair=request.trading_pair,
                    local_status="submitted",
                    remote_confirmed=True,
                    local_record_created=True,
                    remote_started=True,
                    hummingbot_bot_id=matched_bot.get("name") or matched_bot.get("instance_name"),
                    started_at=now,
                    config=config_preview_dict,
                    hummingbot_response=sanitize_data(deploy_resp),
                ),
            )
        else:
            # deploy 返回 200 但 Bot 不在 active 列表中
            # 可能原因：Hummingbot API 容器内没有 Docker CLI，无法真正创建容器
            docker_limitation_msg = (
                "Hummingbot API deploy 接口返回成功（HTTP 200），但该 Bot 未出现在 active_bots 列表中。"
                " 这通常是因为 Hummingbot API 容器内没有 Docker CLI，无法真正创建 Bot 容器。"
                " 请检查：1) docker exec hummingbot-api which docker（验证 docker CLI 是否安装）；"
                " 2) docker logs hummingbot-api（查看容器日志）。"
                " QuantAgent 本地记录已创建（local_record_created=true），但 remote_started=false。"
            )
            record_paper_bot(
                paper_bot_id=paper_bot_id,
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                config=config_preview_dict,
            )
            update_paper_bot_fields(
                paper_bot_id,
                local_status="start_failed",
                last_error=docker_limitation_msg,
            )
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=request.strategy_type.value,
                trading_pair=request.trading_pair,
                success=False,
                error_message=docker_limitation_msg,
                config=config_preview_dict,
            )
            return PaperBotStartResponse(
                local_record_created=True,
                remote_started=False,
                remote_confirmed=False,
                data=PaperBotStartData(
                    paper_bot_id=paper_bot_id,
                    bot_name=request.bot_name,
                    strategy_type=request.strategy_type.value,
                    trading_pair=request.trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                    config=config_preview_dict,
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
    """从 Hummingbot API 获取 active bots（兼容旧/新格式）"""
    try:
        result = await _call_hummingbot_api("GET", "/bot-orchestration/status")
        bots = result.get("data", {}) or {}

        # 旧格式: active_bots / disconnected_bots 是 list
        if isinstance(bots, dict) and ("active_bots" in bots or "disconnected_bots" in bots):
            active = bots.get("active_bots", []) or []
            disconnected = bots.get("disconnected_bots", []) or []
            bots_list = list(active) + list(disconnected)
            return sanitize_data(bots_list), "bot_api"

        # 新格式: data 是 dict，key 是 instance_name
        if isinstance(bots, dict):
            bots_list = [
                {"instance_name": k, **sanitize_data(v)}
                for k, v in bots.items()
                if isinstance(v, dict)
            ]
            if bots_list:
                return bots_list, "bot_api_dict_keys"

        if isinstance(bots, list):
            return sanitize_data(bots), "bot_api"
    except Exception as e:
        logger.warning(f"Failed to fetch active bots: {e}")
    return [], "none"


async def get_paper_bots_list() -> Dict[str, Any]:
    """获取 Paper Bot 列表，并对账 Hummingbot active_bots"""
    now = datetime.utcnow().isoformat() + "Z"
    local_records = get_paper_bot_records()
    remote_bots, matched_by = await _fetch_hummingbot_active_bots()

    remote_bot_map: Dict[str, Dict] = {}
    for bot in remote_bots:
        name = str(bot.get("name") or bot.get("instance_name") or "").lower()
        if name:
            remote_bot_map[name] = bot

    bots = []
    for paper_bot_id, record in local_records.items():
        bot_name = record.get("bot_name", "").lower()
        matched = paper_bot_id.lower() in remote_bot_map or bot_name in remote_bot_map
        if matched:
            matched_hb_bot = remote_bot_map.get(paper_bot_id.lower()) or remote_bot_map.get(bot_name)
            hummingbot_bot_id = (
                matched_hb_bot.get("name") or matched_hb_bot.get("instance_name") or None
            )
            update_paper_bot_fields(
                paper_bot_id,
                remote_status="running",
                local_status="running",
                matched_remote_bot=True,
                matched_by=matched_by,
                hummingbot_bot_id=hummingbot_bot_id,
                last_remote_check_at=now,
            )
        else:
            # 不覆盖本地记录的 local_status 和 last_error
            update_paper_bot_fields(
                paper_bot_id,
                remote_status="not_detected",
                matched_remote_bot=False,
                matched_by="none",
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
            "local_status": record.get("local_status", "submitted"),
            "remote_status": record.get("remote_status", "not_detected"),
            "matched_remote_bot": record.get("matched_remote_bot", False),
            "matched_by": record.get("matched_by", "none"),
            "hummingbot_bot_id": record.get("hummingbot_bot_id"),
            "started_at": started_at,
            "runtime_seconds": runtime,
            "last_error": record.get("last_error"),
        })

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
    """获取 Paper Bot 详情（包含最新对账状态）"""
    now = datetime.utcnow().isoformat() + "Z"
    record = get_paper_bot_record(paper_bot_id)

    if not record:
        return {"connected": False, "source": "quantagent", "data": None, "error": f"Paper Bot '{paper_bot_id}' 不存在"}

    # 重新对账
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
        hummingbot_bot_id = matched_hb_bot.get("name") or matched_hb_bot.get("instance_name") or None
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
    remote_status = record.get("remote_status", "not_detected") if record else "not_detected"

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
    remote_status = record.get("remote_status", "not_detected") if record else "not_detected"

    if remote_status != "running":
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
    remote_status = record.get("remote_status", "not_detected") if record else "not_detected"

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
            "filter_note": "Hummingbot API 暂不支持按 Bot 精确隔离 Portfolio。" if portfolio else "暂无 Portfolio 数据。",
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 日志 ───────────────────────────────────────────────

async def get_paper_bot_logs(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    remote_status = record.get("remote_status", "not_detected") if record else "not_detected"

    logs_message = None
    if remote_status != "running":
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
    now = datetime.utcnow().isoformat() + "Z"

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
