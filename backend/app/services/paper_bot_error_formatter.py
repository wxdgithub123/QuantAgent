"""
Paper Bot 错误消息格式化服务

Phase 4 P3-2: 错误提示优化

将技术性错误代码转换为用户友好的中文提示，
包含：简短说明、详细原因、建议操作和相关文档链接。
"""

from typing import Any, Dict, Optional


# 错误代码 -> 错误信息映射
ERROR_MESSAGES: Dict[str, Dict[str, str]] = {
    # ── 连接类错误 ────────────────────────────────────────────────────────
    "api_offline": {
        "short": "Hummingbot API 不在线",
        "detail": "无法连接到 Hummingbot API 服务（HTTP 连接失败或超时）。",
        "action": "请检查 Hummingbot 容器是否正常运行：docker ps | grep hummingbot",
        "doc_url": "/docs/hummingbot-exchange-connection-guide",
    },
    "api_timeout": {
        "short": "Hummingbot API 请求超时",
        "detail": "向 Hummingbot API 发送请求后未在规定时间内收到响应。",
        "action": "检查 Hummingbot 服务是否过载，或网络连接是否稳定。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide",
    },
    "api_502": {
        "short": "Hummingbot API 网关错误",
        "detail": "Hummingbot 后端服务异常，返回 HTTP 502 Bad Gateway。",
        "action": "重启 Hummingbot 容器：docker restart hummingbot-api",
        "doc_url": "/docs/hummingbot-exchange-connection-guide",
    },
    "api_503": {
        "short": "Hummingbot API 服务不可用",
        "detail": "Hummingbot 后端服务暂时不可用（HTTP 503）。",
        "action": "等待几秒后重试，或检查 Hummingbot 日志：docker logs hummingbot-api",
        "doc_url": "/docs/hummingbot-exchange-connection-guide",
    },
    "api_404": {
        "short": "Hummingbot API 接口不存在",
        "detail": "请求的 Hummingbot API 端点返回 404 Not Found，可能 API 版本不匹配。",
        "action": "确认 Hummingbot 版本与 QuantAgent OS 版本兼容。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide",
    },

    # ── 认证类错误 ────────────────────────────────────────────────────────
    "auth_failed": {
        "short": "Hummingbot API 认证失败",
        "detail": "用户名或密码不正确，无法访问 Hummingbot API。",
        "action": "检查 docker-compose.yml 中的 HUMMINGBOT_API_USERNAME 和 HUMMINGBOT_API_PASSWORD 配置。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide",
    },
    "account_not_found": {
        "short": "未找到 paper_account",
        "detail": "Hummingbot 中没有创建 paper_account，无法进行模拟交易。",
        "action": "请在 Hummingbot 终端中运行：create paper_account",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-account",
    },

    # ── Docker 类错误 ──────────────────────────────────────────────────────
    "docker_cli_missing": {
        "short": "Docker CLI 未安装",
        "detail": "Hummingbot API 容器内无法执行 Docker 命令，无法创建 Bot 容器。",
        "action": "在 docker-compose.yml 中为 hummingbot-api 服务添加 volumes 配置：\n  volumes:\n    - /var/run/docker.sock:/var/run/docker.sock\n    - /usr/bin/docker:/usr/bin/docker",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#docker-cli",
    },
    "docker_permission_denied": {
        "short": "Docker 权限不足",
        "detail": "Hummingbot API 容器无法访问 Docker 守护进程（权限被拒绝）。",
        "action": "确保 hummingbot-api 容器以 privileged 模式运行，或挂载 docker.sock。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#docker-cli",
    },
    "docker_image_not_found": {
        "short": "Docker 镜像未找到",
        "detail": "尝试创建的 Bot 容器所依赖的 Docker 镜像不存在。",
        "action": "确认 Hummingbot 镜像已正确构建并在本地可用。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#docker-cli",
    },

    # ── Bot 操作类错误 ────────────────────────────────────────────────────
    "bot_name_conflict": {
        "short": "Bot 名称冲突",
        "detail": "同名 Bot 已存在，不允许重复创建。",
        "action": "请使用不同的 bot_name，或先停止并删除同名 Bot。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-bot",
    },
    "bot_not_found": {
        "short": "Bot 不存在",
        "detail": "指定 ID 的 Paper Bot 未找到，可能已被停止或删除。",
        "action": "请在 Paper Bot 列表中确认 Bot 状态。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-bot",
    },
    "bot_already_running": {
        "short": "Bot 已在运行",
        "detail": "该 Bot 当前处于运行状态，无法重复启动。",
        "action": "请先停止当前 Bot，再重新启动。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-bot",
    },
    "bot_already_stopped": {
        "short": "Bot 已停止",
        "detail": "该 Bot 当前已处于停止状态。",
        "action": "无需重复停止操作。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-bot",
    },
    "deploy_failed": {
        "short": "Bot 部署失败",
        "detail": "Hummingbot API 的 deploy-v2-controllers 接口返回错误，Bot 未能成功创建。",
        "action": "检查 Hummingbot API 日志以获取详细错误信息。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-bot",
    },
    "deploy_no_confirmation": {
        "short": "缺少停止确认",
        "detail": "停止 Bot 时必须提供 confirm=true 参数，防止误操作。",
        "action": "调用停止接口时，在请求体中添加 confirm: true。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-bot",
    },

    # ── 策略/参数类错误 ──────────────────────────────────────────────────
    "unsupported_strategy": {
        "short": "不支持的策略类型",
        "detail": "当前策略类型尚未支持或映射配置不完整。",
        "action": "支持的策略类型：grid, position_executor, ma, ema, macd, rsi, boll。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#strategy",
    },
    "invalid_trading_pair": {
        "short": "无效的交易对",
        "detail": "交易对格式不正确或不在支持列表中。",
        "action": "请使用标准格式（如 BTC-USDT）并确保交易对在 Hummingbot 支持范围内。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#trading-pair",
    },
    "invalid_connector": {
        "short": "无效的 Connector",
        "detail": "指定的交易所 Connector 不在白名单中。",
        "action": "支持的现货 Connector：binance, kucoin, gate_io, kraken。支持的合约 Connector：binance_perpetual, bybit_perpetual。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#connectors",
    },
    "insufficient_balance": {
        "short": "虚拟资金不足",
        "detail": "Paper Bot 的初始余额不足以执行交易。",
        "action": "增加 paper_initial_balance，建议最低 1000 USDT。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-account",
    },
    "parameter_out_of_range": {
        "short": "参数超出范围",
        "detail": "某个策略参数超出了允许的范围。",
        "action": "请检查各策略参数的 min/max 限制。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#parameters",
    },

    # ── 安全类错误 ────────────────────────────────────────────────────────
    "sensitive_field_detected": {
        "short": "检测到敏感字段",
        "detail": "请求中包含 API Key、Secret 等敏感信息，Paper Bot 不允许使用真实凭证。",
        "action": "请移除所有 API Key 和 Secret，只使用 Paper Bot 模式。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#security",
    },
    "live_or_testnet_forbidden": {
        "short": "禁止实盘/测试网模式",
        "detail": "Paper Bot 接口禁止使用 live 或 testnet 模式。",
        "action": "确保请求中 mode=paper，live_trading=false，testnet=false。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#security",
    },

    # ── Preflight 检查错误 ─────────────────────────────────────────────────
    "preflight_connector_unavailable": {
        "short": "Connector 不可用",
        "detail": "指定的交易所 Connector 当前无法连接。",
        "action": "检查网络连接，确认交易所服务正常。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#connectors",
    },
    "preflight_portfolio_failed": {
        "short": "无法获取 Portfolio 状态",
        "detail": "Preflight 检查时无法获取 Hummingbot Portfolio 信息。",
        "action": "确认 Hummingbot API 正常运行且 paper_account 已创建。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#paper-account",
    },
    "preflight_multiple_failures": {
        "short": "Preflight 检查多项失败",
        "detail": "启动前检查发现多个问题，请逐一修复。",
        "action": "查看详情中的各项错误信息，按建议操作。",
        "doc_url": "/docs/hummingbot-exchange-connection-guide#preflight",
    },
}


def detect_error_code(error_message: str) -> Optional[str]:
    """根据错误消息内容自动检测错误代码"""
    error_lower = error_message.lower()

    if "connection" in error_lower and "timeout" in error_lower:
        return "api_timeout"
    if "502" in error_message or "bad gateway" in error_lower:
        return "api_502"
    if "503" in error_message or "service unavailable" in error_lower:
        return "api_503"
    if "404" in error_message or "not found" in error_lower:
        return "api_404"
    if "auth" in error_lower and ("fail" in error_lower or "unauthorized" in error_lower):
        return "auth_failed"
    if "paper_account" in error_lower and ("not found" in error_lower or "不存在" in error_lower):
        return "account_not_found"
    if "docker" in error_lower and ("not found" in error_lower or "no such file" in error_lower):
        return "docker_cli_missing"
    if "permission denied" in error_lower and "docker" in error_lower:
        return "docker_permission_denied"
    if "already exists" in error_lower or "name conflict" in error_lower:
        return "bot_name_conflict"
    if "not found" in error_lower and "bot" in error_lower:
        return "bot_not_found"
    if "already running" in error_lower:
        return "bot_already_running"
    if "already stopped" in error_lower or "已停止" in error_message:
        return "bot_already_stopped"
    if "deploy" in error_lower and "fail" in error_lower:
        return "deploy_failed"
    if "confirm" in error_lower and ("required" in error_lower or "missing" in error_lower):
        return "deploy_no_confirmation"
    if "unsupported" in error_lower and "strategy" in error_lower:
        return "unsupported_strategy"
    if "invalid" in error_lower and "trading pair" in error_lower:
        return "invalid_trading_pair"
    if "invalid" in error_lower and "connector" in error_lower:
        return "invalid_connector"
    if "insufficient" in error_lower and ("balance" in error_lower or "fund" in error_lower):
        return "insufficient_balance"
    if "api key" in error_lower or "secret" in error_lower or "apikey" in error_lower:
        return "sensitive_field_detected"
    if "live" in error_lower and "forbidden" in error_lower:
        return "live_or_testnet_forbidden"
    if "preflight" in error_lower:
        if "connector" in error_lower:
            return "preflight_connector_unavailable"
        if "portfolio" in error_lower:
            return "preflight_portfolio_failed"
        return "preflight_multiple_failures"

    return None


def format_error(
    error_message: str,
    context: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    格式化错误消息，返回用户友好的错误信息。

    Args:
        error_message: 原始错误消息
        context: 额外的上下文信息（如 paper_bot_id、strategy_type 等）
        error_code: 已知的错误代码（可选，会自动检测）

    Returns:
        格式化的错误信息字典，包含：
        - code: 错误代码
        - short: 简短中文描述
        - detail: 详细原因
        - action: 建议操作
        - doc_url: 相关文档链接
        - context: 上下文信息
        - raw_message: 原始错误消息
    """
    # 优先使用传入的错误代码，否则自动检测
    code = error_code or detect_error_code(error_message) or "unknown"
    error_info = ERROR_MESSAGES.get(code, {})

    return {
        "code": code,
        "short": error_info.get("short", "未知错误"),
        "detail": error_info.get("detail", f"发生了一个未知错误：{error_message}"),
        "action": error_info.get("action", "请联系管理员或查看服务日志。"),
        "doc_url": error_info.get("doc_url", ""),
        "context": context or {},
        "raw_message": error_message,
    }


def format_preflight_errors(errors: list) -> Dict[str, Any]:
    """
    格式化 Preflight 检查错误列表。

    Args:
        errors: 预检查错误列表，每项为 (check_name, is_ok, message) 元组

    Returns:
        格式化的预检查错误信息
    """
    failed = [e for e in errors if not e[1]]  # e = (check_name, is_ok, message)

    if not failed:
        return {"passed": True, "total": len(errors), "failed": []}

    formatted_failed = []
    for check_name, _, message in failed:
        formatted_failed.append(format_error(
            error_message=message,
            context={"check_name": check_name},
            error_code="preflight_multiple_failures",
        ))

    return {
        "passed": False,
        "total": len(errors),
        "failed_count": len(failed),
        "failed": formatted_failed,
    }
