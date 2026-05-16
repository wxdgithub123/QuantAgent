"""
Hummingbot Testnet Perpetual Bot Service

v1.3.x: Testnet 永续合约 Bot

核心设计：
1. 使用 binance_perpetual_testnet（测试网 API Key）
2. 对接 Hummingbot directional_trading controller
3. 不动真钱，走交易所测试环境
4. 所有字段与 Hummingbot 真实 Pydantic schema 完全对齐
5. credentials_profile 使用独立的测试网账户，不复用 master_account
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.schemas.hummingbot_testnet_bot import (
    ALLOWED_TESTNET_ACCOUNTS,
    ALLOWED_TESTNET_CONNECTORS,
    TestnetBotPreviewRequest,
    TestnetBotPreviewResponse,
    TestnetBotPreviewData,
    TestnetBotStartRequest,
    TestnetBotStartResponse,
    TestnetBotStartData,
    TestnetControllerConfig,
)


logger = logging.getLogger(__name__)


# ── 敏感字段 ──────────────────────────────────────────────────────────────

SENSITIVE_KEYS = [
    "api_key", "apikey", "apiSecret", "api_secret", "secret",
    "private_key", "privateKey", "exchange_secret", "exchangeSecret",
    "password", "passphrase", "token",
]


def sanitize_data(data: Any, depth: int = 0) -> Any:
    """脱敏处理"""
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
    auth = httpx.BasicAuth(username, password) if username and password else None

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

_testnet_bot_records: Dict[str, Dict[str, Any]] = {}


def record_testnet_bot(
    testnet_bot_id: str,
    bot_name: str,
    connector: str,
    credentials_profile: str,
    controller_name: str,
    trading_pair: str,
    config: Dict[str, Any],
) -> None:
    """创建本地记录"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _testnet_bot_records[testnet_bot_id] = {
        "testnet_bot_id": testnet_bot_id,
        "bot_name": bot_name,
        "connector": connector,
        "credentials_profile": credentials_profile,
        "controller_name": controller_name,
        "trading_pair": trading_pair,
        "mode": "testnet",
        "market_type": "perpetual",
        "live_trading": False,
        "testnet": True,
        "uses_real_exchange_account": False,
        "requires_api_key": True,
        "local_status": "submitted",
        "remote_status": "not_detected",
        "matched_remote_bot": False,
        "matched_by": "none",
        "hummingbot_bot_id": None,
        "can_fetch_runtime_data": False,
        "started_at": now,
        "created_at": now,
        "config": config,
        "last_error": None,
    }


def update_testnet_bot_fields(testnet_bot_id: str, **fields) -> None:
    if testnet_bot_id in _testnet_bot_records:
        _testnet_bot_records[testnet_bot_id].update(fields)


def get_testnet_bot_records() -> Dict[str, Dict[str, Any]]:
    return _testnet_bot_records


def get_testnet_bot_record(testnet_bot_id: str) -> Optional[Dict[str, Any]]:
    return _testnet_bot_records.get(testnet_bot_id)


# ── Payload 生成 ────────────────────────────────────────────────────────────────

def _normalize_timeframe(timeframe: str) -> str:
    """规范化时间周期"""
    mapping = {
        "1m": "1m", "m1": "1m",
        "3m": "3m", "m3": "3m",
        "5m": "5m", "m5": "5m",
        "15m": "15m", "m15": "15m",
        "1h": "1h", "h1": "1h",
        "4h": "4h", "h4": "4h",
    }
    return mapping.get(timeframe.lower(), "15m")


def build_testnet_controller_payload(
    config_id: str,
    controller_name: str,
    connector: str,
    trading_pair: str,
    timeframe: str,
    total_amount_quote: float,
    leverage: int,
    position_mode: str,
    stop_loss_pct: float,
    take_profit_pct: float,
    cooldown_minutes: int,
    time_limit_minutes: int,
    max_executors_per_side: int,
    bb_length: int,
    bb_std: float,
    bb_long_threshold: float,
    bb_short_threshold: float,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
) -> Dict[str, Any]:
    """
    生成 Hummingbot directional_trading controller 配置 payload。

    字段与 Hummingbot 镜像中真实 Pydantic schema 完全对齐：
    - BollingerV1ControllerConfig
    - MACDBBV1ControllerConfig

    严禁发送 extra 字段（Pydantic extra_forbidden）。
    """
    stop_loss = float(round(stop_loss_pct / 100.0, 6))
    take_profit = float(round(take_profit_pct / 100.0, 6))
    total_amount = float(total_amount_quote)
    cooldown_seconds = int(cooldown_minutes * 60)
    time_limit_seconds = int(time_limit_minutes * 60)

    base: Dict[str, Any] = {
        "id": config_id,
        "controller_type": "directional_trading",
        "controller_name": controller_name,
        "connector_name": connector,
        "trading_pair": trading_pair.upper(),
        "total_amount_quote": total_amount,
        "leverage": leverage,
        "position_mode": position_mode,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "cooldown_time": max(cooldown_seconds, 60),
        "time_limit": max(time_limit_seconds, 60),
        "max_executors_per_side": max_executors_per_side,
        "interval": _normalize_timeframe(timeframe),
    }

    if controller_name == "bollinger_v1":
        base.update({
            "bb_length": bb_length,
            "bb_std": bb_std,
            "bb_long_threshold": bb_long_threshold,
            "bb_short_threshold": bb_short_threshold,
        })

    elif controller_name == "macd_bb_v1":
        base.update({
            "bb_length": bb_length,
            "bb_std": bb_std,
            "bb_long_threshold": bb_long_threshold,
            "bb_short_threshold": bb_short_threshold,
            "macd_fast": macd_fast,
            "macd_slow": macd_slow,
            "macd_signal": macd_signal,
        })

    # supertrend_v1 使用不同的字段名
    elif controller_name == "supertrend_v1":
        base.update({
            "length": 20,
            "multiplier": 4.0,
            "percentage_threshold": 0.01,
        })

    return base


# ── Preview ────────────────────────────────────────────────────────────────────

def _check_sensitive_fields(data: Dict[str, Any]) -> Optional[str]:
    """检查敏感字段"""
    for key in data.keys():
        key_lower = key.lower()
        for pattern in SENSITIVE_KEYS:
            if pattern.lower() in key_lower:
                return f"检测到敏感字段: '{key}'。禁止提交 API Key、Secret 或私钥。"
    return None


async def generate_testnet_bot_preview(
    request: TestnetBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> TestnetBotPreviewResponse:
    """生成 Testnet Bot 配置预览"""
    try:
        if raw_request_data:
            if err := _check_sensitive_fields(raw_request_data):
                return TestnetBotPreviewResponse(valid=False, error=err)

        config_id = f"testnet_{request.bot_name.replace('-', '_')}_{uuid.uuid4().hex[:8]}"

        payload = build_testnet_controller_payload(
            config_id=config_id,
            controller_name=request.controller_name,
            connector=request.connector,
            trading_pair=request.trading_pair,
            timeframe=request.timeframe.value,
            total_amount_quote=request.total_amount_quote,
            leverage=request.leverage,
            position_mode=request.position_mode.value,
            stop_loss_pct=request.stop_loss_pct,
            take_profit_pct=request.take_profit_pct,
            cooldown_minutes=request.cooldown_minutes,
            time_limit_minutes=request.time_limit_minutes,
            max_executors_per_side=request.max_executors_per_side,
            bb_length=request.bb_length,
            bb_std=request.bb_std,
            bb_long_threshold=request.bb_long_threshold,
            bb_short_threshold=request.bb_short_threshold,
            macd_fast=request.macd_fast,
            macd_slow=request.macd_slow,
            macd_signal=request.macd_signal,
        )

        warnings = [
            "当前为 Testnet 永续合约 Bot，使用交易所测试环境。",
            "不动真钱，但需要测试网 API Key。",
            "请勿填写主网 API Key。",
            f"Connector: {request.connector}",
            f"Controller: directional_trading/{request.controller_name}",
            f"杠杆: {request.leverage}x | 持仓模式: {request.position_mode.value}",
        ]

        preview_data = TestnetBotPreviewData(
            controller_config=TestnetControllerConfig(**payload),
            warnings=warnings,
        )
        return TestnetBotPreviewResponse(valid=True, data=preview_data)

    except Exception as e:
        return TestnetBotPreviewResponse(valid=False, error=f"生成预览时发生错误: {str(e)}")


# ── Start ─────────────────────────────────────────────────────────────────────

async def start_testnet_bot(
    request: TestnetBotStartRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> TestnetBotStartResponse:
    """启动 Testnet Bot"""
    try:
        if raw_request_data:
            if err := _check_sensitive_fields(raw_request_data):
                return TestnetBotStartResponse(
                    local_record_created=False, remote_started=False, remote_confirmed=False,
                    error=err,
                )

        testnet_bot_id = f"testnet_{request.bot_name}_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        config_id = f"testnet_{request.bot_name.replace('-', '_')}_{uuid.uuid4().hex[:8]}"

        payload = build_testnet_controller_payload(
            config_id=config_id,
            controller_name=request.controller_name,
            connector=request.connector,
            trading_pair=request.trading_pair,
            timeframe=request.timeframe.value,
            total_amount_quote=request.total_amount_quote,
            leverage=request.leverage,
            position_mode=request.position_mode.value,
            stop_loss_pct=request.stop_loss_pct,
            take_profit_pct=request.take_profit_pct,
            cooldown_minutes=request.cooldown_minutes,
            time_limit_minutes=request.time_limit_minutes,
            max_executors_per_side=request.max_executors_per_side,
            bb_length=request.bb_length,
            bb_std=request.bb_std,
            bb_long_threshold=request.bb_long_threshold,
            bb_short_threshold=request.bb_short_threshold,
            macd_fast=request.macd_fast,
            macd_slow=request.macd_slow,
            macd_signal=request.macd_signal,
        )

        # ── Step 1: 创建本地记录 ──────────────────────────────────────
        record_testnet_bot(
            testnet_bot_id=testnet_bot_id,
            bot_name=request.bot_name,
            connector=request.connector,
            credentials_profile=request.credentials_profile,
            controller_name=request.controller_name,
            trading_pair=request.trading_pair,
            config=payload,
        )

        # ── Step 2: 验证 credentials_profile 存在 ───────────────────────
        try:
            accounts_resp = await _call_hummingbot_api("GET", "/accounts/")
            accounts = accounts_resp if isinstance(accounts_resp, list) else accounts_resp.get("data", [])
            if request.credentials_profile not in accounts:
                update_testnet_bot_fields(
                    testnet_bot_id,
                    local_status="start_failed",
                    last_error=f"credentials_profile '{request.credentials_profile}' 不存在。可用账户: {accounts}"
                )
                return TestnetBotStartResponse(
                    local_record_created=True,
                    remote_started=False,
                    remote_confirmed=False,
                    data=TestnetBotStartData(
                        testnet_bot_id=testnet_bot_id,
                        bot_name=request.bot_name,
                        connector=request.connector,
                        credentials_profile=request.credentials_profile,
                        controller_name=request.controller_name,
                        trading_pair=request.trading_pair,
                        local_status="start_failed",
                        remote_confirmed=False,
                        local_record_created=True,
                        remote_started=False,
                        started_at=now,
                    ),
                    error=f"credentials_profile '{request.credentials_profile}' 不存在于 Hummingbot 中。"
                          f" 请先在 Hummingbot 中导入测试网 API Key。",
                )
        except Exception as e:
            update_testnet_bot_fields(
                testnet_bot_id,
                local_status="start_failed",
                last_error=f"验证账户失败: {str(e)}"
            )
            return TestnetBotStartResponse(
                local_record_created=True, remote_started=False, remote_confirmed=False,
                data=TestnetBotStartData(
                    testnet_bot_id=testnet_bot_id,
                    bot_name=request.bot_name,
                    connector=request.connector,
                    credentials_profile=request.credentials_profile,
                    controller_name=request.controller_name,
                    trading_pair=request.trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                ),
                error=f"无法验证 credentials_profile: {str(e)}",
            )

        # ── Step 3: 创建 controller config ────────────────────────────
        try:
            await _call_hummingbot_api(
                "POST",
                f"/controllers/configs/{config_id}",
                json_data=payload,
                timeout=20.0,
            )
        except Exception as e:
            update_testnet_bot_fields(
                testnet_bot_id,
                local_status="start_failed",
                last_error=f"创建 controller config 失败: {str(e)}"
            )
            return TestnetBotStartResponse(
                local_record_created=True,
                remote_started=False,
                remote_confirmed=False,
                data=TestnetBotStartData(
                    testnet_bot_id=testnet_bot_id,
                    bot_name=request.bot_name,
                    connector=request.connector,
                    credentials_profile=request.credentials_profile,
                    controller_name=request.controller_name,
                    trading_pair=request.trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                ),
                error=f"创建 controller config 失败: {str(e)}",
            )

        # ── Step 4: 调用 deploy ───────────────────────────────────────
        deploy_payload = {
            "instance_name": testnet_bot_id,
            "credentials_profile": request.credentials_profile,
            "controllers_config": [config_id],
            "headless": True,
        }

        deploy_resp: Optional[Dict[str, Any]] = None
        try:
            deploy_resp = await _call_hummingbot_api(
                "POST",
                "/bot-orchestration/deploy-v2-controllers",
                json_data=deploy_payload,
                timeout=30.0,
            )
        except Exception as e:
            update_testnet_bot_fields(
                testnet_bot_id,
                local_status="start_failed",
                last_error=f"deploy 失败: {str(e)}"
            )
            return TestnetBotStartResponse(
                local_record_created=True,
                remote_started=False,
                remote_confirmed=False,
                data=TestnetBotStartData(
                    testnet_bot_id=testnet_bot_id,
                    bot_name=request.bot_name,
                    connector=request.connector,
                    credentials_profile=request.credentials_profile,
                    controller_name=request.controller_name,
                    trading_pair=request.trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                    config=payload,
                ),
                error=f"deploy 失败: {str(e)}",
            )

        # ── Step 5: 验证 active_bots ────────────────────────────────
        found, matched_bot = await _verify_bot_in_active_list(testnet_bot_id, request.bot_name)

        if found and matched_bot:
            update_testnet_bot_fields(
                testnet_bot_id,
                local_status="submitted",
                remote_status="running",
                matched_remote_bot=True,
                matched_by="active_bots",
                hummingbot_bot_id=matched_bot.get("name") or matched_bot.get("instance_name"),
                can_fetch_runtime_data=True,
            )
            return TestnetBotStartResponse(
                local_record_created=True,
                remote_started=True,
                remote_confirmed=True,
                data=TestnetBotStartData(
                    testnet_bot_id=testnet_bot_id,
                    bot_name=request.bot_name,
                    connector=request.connector,
                    credentials_profile=request.credentials_profile,
                    controller_name=request.controller_name,
                    trading_pair=request.trading_pair,
                    local_status="submitted",
                    remote_confirmed=True,
                    local_record_created=True,
                    remote_started=True,
                    hummingbot_bot_id=matched_bot.get("name") or matched_bot.get("instance_name"),
                    started_at=now,
                    config=payload,
                    hummingbot_response=sanitize_data(deploy_resp),
                ),
            )
        else:
            msg = (
                "deploy 接口返回成功，但 Bot 未出现在 active_bots 中。"
                " 请检查 Hummingbot API 日志确认 Bot 是否真正启动。"
            )
            update_testnet_bot_fields(
                testnet_bot_id,
                local_status="submitted",
                remote_status="deployed",
                matched_remote_bot=True,
                matched_by="bot_runs",
                can_fetch_runtime_data=False,
                last_error=msg,
            )
            return TestnetBotStartResponse(
                local_record_created=True,
                remote_started=True,
                remote_confirmed=False,
                data=TestnetBotStartData(
                    testnet_bot_id=testnet_bot_id,
                    bot_name=request.bot_name,
                    connector=request.connector,
                    credentials_profile=request.credentials_profile,
                    controller_name=request.controller_name,
                    trading_pair=request.trading_pair,
                    local_status="submitted",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=True,
                    started_at=now,
                    config=payload,
                    hummingbot_response=sanitize_data(deploy_resp),
                ),
                error=msg,
            )

    except Exception as e:
        return TestnetBotStartResponse(
            local_record_created=False,
            remote_started=False,
            remote_confirmed=False,
            error=f"启动 Testnet Bot 时发生错误: {str(e)}",
        )


# ── 验证 Bot 在 active_bots 中 ─────────────────────────────────────────────────

async def _verify_bot_in_active_list(
    instance_name: str,
    bot_name: str,
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """验证 Bot 是否在 Hummingbot 活跃列表中"""
    inst_lower = instance_name.lower()
    bot_lower = bot_name.lower()

    try:
        status_resp = await _call_hummingbot_api("GET", "/bot-orchestration/status", timeout=10.0)
        data = status_resp.get("data", {}) or {}

        if isinstance(data, dict) and ("active_bots" in data or "disconnected_bots" in data):
            active = data.get("active_bots", []) or []
            disconnected = data.get("disconnected_bots", []) or []
            all_bots = list(active) + list(disconnected)
            for bot in all_bots:
                name = str(bot.get("name") or bot.get("instance_name") or "").lower()
                if inst_lower in name or bot_lower in name or name in inst_lower:
                    return True, sanitize_data(bot)

        if isinstance(data, dict):
            for key, bot_info in data.items():
                key_lower = key.lower()
                if inst_lower in key_lower or bot_lower in key_lower or key_lower in inst_lower:
                    return True, sanitize_data(bot_info)

    except Exception:
        pass

    try:
        runs_resp = await _call_hummingbot_api("GET", "/bot-orchestration/bot-runs", timeout=10.0)
        runs_data = runs_resp.get("data", [])
        if not isinstance(runs_data, list):
            runs_data = runs_resp.get("data", {}).get("data", [])

        for run in runs_data:
            run_instance = str(run.get("instance_name") or run.get("bot_name") or "").lower()
            if inst_lower in run_instance or bot_lower in run_instance:
                return True, sanitize_data(run)
    except Exception:
        pass

    return False, None


# ── 列表 / 详情 ────────────────────────────────────────────────────────────────

async def get_testnet_bots_list() -> Dict[str, Any]:
    """获取 Testnet Bot 列表"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    local_records = get_testnet_bot_records()

    bots = []
    for testnet_bot_id, record in local_records.items():
        runtime = 0
        started_at = record.get("started_at") or record.get("created_at")
        if started_at:
            try:
                started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                runtime = int((datetime.now().astimezone() - started_dt).total_seconds())
            except Exception:
                pass

        bots.append({
            "testnet_bot_id": testnet_bot_id,
            "bot_name": record["bot_name"],
            "connector": record["connector"],
            "credentials_profile": record.get("credentials_profile", ""),
            "controller_name": record.get("controller_name", "bollinger_v1"),
            "trading_pair": record["trading_pair"],
            "mode": "testnet",
            "market_type": "perpetual",
            "live_trading": False,
            "testnet": True,
            "uses_real_exchange_account": False,
            "requires_api_key": True,
            "local_status": record["local_status"],
            "remote_status": record["remote_status"],
            "matched_remote_bot": record["matched_remote_bot"],
            "matched_by": record["matched_by"],
            "hummingbot_bot_id": record.get("hummingbot_bot_id"),
            "can_fetch_runtime_data": record["can_fetch_runtime_data"],
            "started_at": started_at,
            "runtime_seconds": runtime,
            "last_error": record.get("last_error"),
        })

    bots.sort(key=lambda b: b.get("started_at") or "", reverse=True)
    return {
        "connected": True,
        "source": "quantagent",
        "mode": "testnet",
        "data": {"bots": bots, "last_check_at": now},
        "error": None,
    }


async def get_testnet_bot_detail(testnet_bot_id: str) -> Dict[str, Any]:
    """获取 Testnet Bot 详情"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = get_testnet_bot_record(testnet_bot_id)

    if not record:
        return {"connected": False, "source": "quantagent", "data": None, "error": f"Bot '{testnet_bot_id}' 不存在"}

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
            "testnet_bot_id": testnet_bot_id,
            "bot_name": record["bot_name"],
            "connector": record["connector"],
            "credentials_profile": record.get("credentials_profile", ""),
            "controller_name": record.get("controller_name", "bollinger_v1"),
            "trading_pair": record["trading_pair"],
            "mode": "testnet",
            "market_type": "perpetual",
            "live_trading": False,
            "testnet": True,
            "uses_real_exchange_account": False,
            "requires_api_key": True,
            "local_status": record["local_status"],
            "remote_status": record["remote_status"],
            "matched_remote_bot": record["matched_remote_bot"],
            "matched_by": record["matched_by"],
            "hummingbot_bot_id": record.get("hummingbot_bot_id"),
            "can_fetch_runtime_data": record["can_fetch_runtime_data"],
            "started_at": started_at,
            "runtime_seconds": runtime,
            "config": sanitize_data(record.get("config", {})),
            "last_error": record.get("last_error"),
        },
        "error": None,
    }


async def stop_testnet_bot(
    testnet_bot_id: str,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """停止 Testnet Bot"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    confirm = raw_request_data.get("confirm") if raw_request_data else None
    if confirm is not True:
        return {
            "stopped": False,
            "mode": "testnet",
            "data": None,
            "error": "缺少 confirm=true",
            "timestamp": now,
        }

    record = get_testnet_bot_record(testnet_bot_id)
    if not record:
        return {
            "stopped": False,
            "mode": "testnet",
            "data": None,
            "error": f"Bot '{testnet_bot_id}' 不存在",
            "timestamp": now,
        }

    update_testnet_bot_fields(testnet_bot_id, local_status="stopping")

    stop_success = False
    stop_error: Optional[str] = None
    hummingbot_response = None

    try:
        stop_payload = {
            "bot_name": record.get("bot_name", testnet_bot_id),
            "skip_order_cancellation": True,
            "async_backend": False,
        }
        hummingbot_response = await _call_hummingbot_api(
            "POST", "/bot-orchestration/stop-bot", json_data=stop_payload
        )
        stop_success = True
    except Exception as e:
        stop_error = str(e)

    update_testnet_bot_fields(
        testnet_bot_id,
        local_status="stopped" if stop_success else "unknown",
        remote_status="not_detected",
        matched_remote_bot=False,
        matched_by="none",
    )

    return {
        "stopped": stop_success,
        "source": "hummingbot-api" if stop_success else "quantagent",
        "mode": "testnet",
        "data": {
            "testnet_bot_id": testnet_bot_id,
            "bot_name": record["bot_name"],
            "local_status": "stopped" if stop_success else "unknown",
            "stopped_at": now if stop_success else None,
            "hummingbot_response": sanitize_data(hummingbot_response),
        } if stop_success else None,
        "error": stop_error,
        "timestamp": now,
    }
