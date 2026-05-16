"""
Hummingbot API Endpoints (Read-only + Paper Bot)

提供只读访问 Hummingbot API 的 REST 接口，以及 QuantAgent Paper Bot 管理接口。

只读接口：
- GET /hummingbot/status     - API 连接状态
- GET /hummingbot/docker     - Docker 容器状态
- GET /hummingbot/connectors - Connectors 列表
- GET /hummingbot/portfolio  - Portfolio 信息
- GET /hummingbot/bots       - Bots 编排状态
- GET /hummingbot/orders     - 订单信息（只读）
- GET /hummingbot/positions  - 持仓信息（只读）

Paper Bot（v1.2.x）：纯现货模拟盘，不接 API Key
- POST /hummingbot/paper-bots/preview
- POST /hummingbot/paper-bots/start
- GET  /hummingbot/paper-bots
- GET  /hummingbot/paper-bots/{id}
- GET  /hummingbot/paper-bots/{id}/orders
- GET  /hummingbot/paper-bots/{id}/positions
- GET  /hummingbot/paper-bots/{id}/portfolio
- GET  /hummingbot/paper-bots/{id}/logs
- POST /hummingbot/paper-bots/{id}/stop

Testnet Perpetual Bot（v1.3.x）：测试网永续合约，需要测试网 API Key
- POST /hummingbot/testnet-bots/preview
- POST /hummingbot/testnet-bots/start
- GET  /hummingbot/testnet-bots
- GET  /hummingbot/testnet-bots/{id}
- POST /hummingbot/testnet-bots/{id}/stop

注意：
- 所有只读接口仅返回数据，不执行真实交易
- Paper Bot 接口仅用于本地模拟，不支持 directional_trading controller
- Testnet Bot 使用测试网 API Key，不动真钱
- 不暴露 Hummingbot API 认证信息到前端
"""

from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.hummingbot_api_service import (
    get_hummingbot_service,
    HummingbotAPIError,
)
from app.services.hummingbot_paper_bot_service import (
    generate_paper_bot_preview,
    start_paper_bot,
    get_paper_connectors,
    get_paper_bots_list,
    get_paper_bot_detail,
    get_paper_bot_orders as svc_get_paper_bot_orders,
    get_paper_bot_positions as svc_get_paper_bot_positions,
    get_paper_bot_portfolio as svc_get_paper_bot_portfolio,
    get_paper_bot_logs as svc_get_paper_bot_logs,
    stop_paper_bot,
)
from app.schemas.hummingbot_paper_bot import (
    PaperBotPreviewRequest,
    PaperBotPreviewResponse,
    PaperBotStartResponse,
    PaperConnectorResponse,
)


router = APIRouter()


class HummingbotResponse(BaseModel):
    """统一响应格式"""
    connected: bool
    source: str = "hummingbot-api"
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: str


def make_response(connected: bool, data: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    """构建统一响应"""
    return {
        "connected": connected,
        "source": "hummingbot-api",
        "data": data,
        "error": error,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/status", response_model=HummingbotResponse)
async def get_status():
    """
    获取 Hummingbot API 连接状态

    这是最基础的接口，必须尽量稳定。
    即使 Hummingbot API 不在线，也返回 connected=false，而不是 500。
    """
    try:
        service = get_hummingbot_service()
        data = await service.get_status()
        return make_response(connected=True, data=data)
    except HummingbotAPIError as e:
        # 连接失败或认证失败，都返回 connected=false
        return make_response(connected=False, error=e.message)
    except Exception as e:
        return make_response(connected=False, error=f"未知错误: {str(e)}")


@router.get("/docker", response_model=HummingbotResponse)
async def get_docker():
    """
    获取 Docker 容器状态

    返回运行中的容器和活跃容器信息。
    """
    try:
        service = get_hummingbot_service()

        # 尝试获取 /docker/running
        running_data = None
        try:
            running_data = await service.get_docker_running()
        except HummingbotAPIError as e:
            # 404 是正常的，某些版本可能没有此端点
            if e.status_code != 404:
                raise

        # 尝试获取 /docker/active-containers
        active_data = None
        try:
            active_data = await service.get_active_containers()
        except HummingbotAPIError as e:
            if e.status_code != 404:
                raise

        data = {
            "docker_running": running_data,
            "active_containers": active_data,
        }

        return make_response(connected=True, data=data)
    except HummingbotAPIError as e:
        return make_response(connected=False, error=e.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


@router.get("/connectors", response_model=HummingbotResponse)
async def get_connectors():
    """
    获取支持的 Connectors 列表
    """
    try:
        service = get_hummingbot_service()
        data = await service.get_connectors()
        return make_response(connected=True, data=data)
    except HummingbotAPIError as e:
        return make_response(connected=False, error=e.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


@router.get("/paper-connectors", response_model=PaperConnectorResponse)
async def get_paper_connectors_endpoint():
    """
    获取当前 Hummingbot 可用的 Paper Bot connector 列表。

    功能：
    1. 调用 Hummingbot /connectors 接口
    2. 过滤出 Paper Bot 允许的现货 connector
    3. 返回可用 connector 列表

    返回示例（有可用 connector）：
    {
        "connected": true,
        "data": {
            "paper_connectors": ["binance"],
            "available": true,
            "message": null
        }
    }

    返回示例（无可用 connector）：
    {
        "connected": true,
        "data": {
            "paper_connectors": [],
            "available": false,
            "message": "当前 Hummingbot 未检测到可用 paper connector。"
        }
    }
    """
    try:
        result = await get_paper_connectors()
        return result
    except Exception as e:
        return PaperConnectorResponse(
            connected=False,
            data={
                "paper_connectors": [],
                "available": False,
                "message": f"获取 Paper Connector 时发生错误: {str(e)}",
            },
            error=str(e),
        )


@router.get("/portfolio", response_model=HummingbotResponse)
async def get_portfolio():
    """
    获取 Portfolio 实盘资产信息

    优先使用 POST /portfolio/state 获取当前 portfolio 状态。
    如果返回 404，同时尝试 GET /accounts/ 获取账户列表。
    返回统一格式的响应数据。
    """
    try:
        service = get_hummingbot_service()

        # 优先尝试 /portfolio/state
        portfolio_data = None
        accounts_data = None
        data_source = None

        try:
            portfolio_result = await service.get_portfolio_state()
            if portfolio_result:
                portfolio_data = portfolio_result
                data_source = "portfolio_state"
        except HummingbotAPIError as e:
            if e.status_code != 404:
                raise

        # 尝试获取账户列表
        try:
            accounts_result = await service.get_accounts()
            if accounts_result:
                accounts_data = accounts_result
        except HummingbotAPIError:
            pass

        # 组合返回数据
        data = {
            "portfolio_state": portfolio_data,
            "accounts": accounts_data,
            "source": data_source,
        }

        # 判断是否有有效数据
        has_data = (portfolio_data and len(str(portfolio_data)) > 10) or \
                   (accounts_data and len(str(accounts_data)) > 10)

        return make_response(
            connected=has_data,
            data=data,
            error=None if has_data else "当前 Hummingbot API 未返回有效的 portfolio 数据"
        )

    except HummingbotAPIError as e:
        if e.status_code == 404:
            return make_response(
                connected=False,
                error=f"当前 Hummingbot API 版本未提供 portfolio 接口，请以 Swagger /docs 为准。"
            )
        return make_response(connected=False, error=e.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


@router.get("/bots", response_model=HummingbotResponse)
async def get_bots():
    """
    获取 Bots 编排状态

    优先从 /bot-orchestration/status 获取活跃 bots 状态。
    如果返回 404，说明当前 Hummingbot API 版本不支持 bot 编排接口，
    则降级使用 /docker/active-containers 中筛选 hummingbot 相关容器作为备选数据源。
    """
    try:
        service = get_hummingbot_service()

        # 优先尝试 /bot-orchestration/status
        bots_data = None
        bot_source = None
        try:
            bots_result = await service.get_bots()
            # 解析返回数据，兼容空数据情况
            if bots_result and isinstance(bots_result, dict):
                if bots_result.get("data") and len(bots_result["data"]) > 0:
                    bots_data = bots_result["data"]
                    bot_source = "bot-orchestration"
        except HummingbotAPIError as e:
            if e.status_code != 404:
                raise

        # 如果 bot-orchestration 没有数据，尝试获取 MQTT 状态
        if bots_data is None:
            try:
                mqtt_result = await service.get_bots_mqtt()
                if mqtt_result and isinstance(mqtt_result, dict):
                    if mqtt_result.get("data") or mqtt_result.get("discovered_bots"):
                        bots_data = mqtt_result.get("data") or {"discovered_bots": mqtt_result.get("discovered_bots")}
                        bot_source = "bot-orchestration-mqtt"
            except HummingbotAPIError:
                pass

        # 如果 bot-orchestration 完全不可用（404），降级使用 active containers
        containers_data = None
        try:
            containers_data = await service.get_active_containers()
        except HummingbotAPIError:
            pass

        # 组合返回数据
        data = {
            "source": bot_source or "docker-containers",
            "bots": bots_data,
            "mqtt_data": None if bot_source else None,
            "containers_fallback": None,
        }

        # 如果使用 Docker containers 作为降级数据源
        if bot_source is None and containers_data:
            # 筛选 hummingbot 相关的容器
            hummingbot_containers = []
            if isinstance(containers_data, list):
                for container in containers_data:
                    name = container.get("name", "")
                    image = container.get("image", "")
                    # 匹配 hummingbot 相关容器
                    if "hummingbot" in name.lower() or "hummingbot" in image.lower():
                        hummingbot_containers.append({
                            "container_name": name,
                            "status": container.get("status", "unknown"),
                            "image": image,
                            "source": "docker"
                        })

            data["containers_fallback"] = {
                "containers": hummingbot_containers,
                "total": len(hummingbot_containers),
                "note": "当前 Hummingbot API 版本未提供 bot 编排接口，已使用 Docker 容器信息作为临时数据源。"
            }

        # 判断是否有数据
        has_bots = (bots_data and len(str(bots_data)) > 2) or \
                   (data["containers_fallback"] and data["containers_fallback"]["total"] > 0)

        return make_response(
            connected=has_bots,
            data=data,
            error=None
        )

    except HummingbotAPIError as e:
        return make_response(connected=False, error=e.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


@router.get("/orders", response_model=HummingbotResponse)
async def get_orders():
    """
    获取实盘订单信息

    优先获取活跃订单（/trading/orders/active）。
    如果返回 404，尝试搜索历史订单（/trading/orders/search）。
    只读操作，不执行下单或撤单。
    """
    try:
        service = get_hummingbot_service()

        active_orders = None
        history_orders = None
        source = None

        # 优先尝试获取活跃订单
        try:
            result = await service.get_active_orders()
            if result:
                # 兼容分页格式
                if isinstance(result, dict):
                    active_orders = result.get("data") or result
                else:
                    active_orders = result
                source = "orders_active"
        except HummingbotAPIError as e:
            if e.status_code != 404:
                raise

        # 如果没有活跃订单，尝试搜索历史订单（最近24小时）
        if active_orders is None:
            try:
                import time
                end_time = int(time.time() * 1000)
                start_time = end_time - 86400000  # 24小时前
                result = await service.search_orders({
                    "start_time": start_time,
                    "end_time": end_time,
                })
                if result:
                    if isinstance(result, dict):
                        history_orders = result.get("data") or result
                    else:
                        history_orders = result
                    source = "orders_search"
            except HummingbotAPIError:
                pass

        # 组合返回数据
        data = {
            "source": source,
            "active_orders": active_orders,
            "history_orders": history_orders,
        }

        # 判断是否有数据
        has_orders = (
            (active_orders and (isinstance(active_orders, list) and len(active_orders) > 0 or len(str(active_orders)) > 10)) or
            (history_orders and (isinstance(history_orders, list) and len(history_orders) > 0 or len(str(history_orders)) > 10))
        )

        return make_response(
            connected=has_orders,
            data=data,
            error=None if has_orders else "当前 Hummingbot API 未返回有效的订单数据"
        )

    except HummingbotAPIError as e:
        if e.status_code == 404:
            return make_response(
                connected=False,
                error=f"当前 Hummingbot API 版本未提供订单接口，请以 Swagger /docs 为准。"
            )
        return make_response(connected=False, error=e.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


@router.get("/positions", response_model=HummingbotResponse)
async def get_positions():
    """
    获取实盘持仓信息

    使用 /trading/positions 接口获取当前开仓的永续合约持仓。
    只读操作，不执行平仓。
    """
    try:
        service = get_hummingbot_service()

        positions_data = None
        source = None

        try:
            result = await service.get_positions()
            if result:
                # 兼容分页格式
                if isinstance(result, dict):
                    positions_data = result.get("data") or result
                else:
                    positions_data = result
                source = "trading_positions"
        except HummingbotAPIError as e:
            if e.status_code != 404:
                raise

        data = {
            "source": source,
            "positions": positions_data,
        }

        # 判断是否有数据
        has_positions = (
            positions_data and
            (isinstance(positions_data, list) and len(positions_data) > 0 or len(str(positions_data)) > 10)
        )

        return make_response(
            connected=has_positions,
            data=data,
            error=None if has_positions else "当前 Hummingbot API 未返回有效的持仓数据"
        )

    except HummingbotAPIError as e:
        if e.status_code == 404:
            return make_response(
                connected=False,
                error=f"当前 Hummingbot API 版本未提供持仓接口，请以 Swagger /docs 为准。"
            )
        return make_response(connected=False, error=e.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


# ── Paper Bot 配置预览 (v1.2.1) ─────────────────────────────────────────────────

@router.post("/paper-bots/preview", response_model=PaperBotPreviewResponse)
async def preview_paper_bot(
    paper_bot_request: PaperBotPreviewRequest,
    raw_request: Request,
):
    """
    生成 Hummingbot Paper Bot 配置预览。

    v1.2.1 阶段仅生成配置预览，不启动 Bot，不执行真实交易。

    功能：
    1. 接收用户提交的 Paper Bot 配置参数
    2. 后端安全校验（敏感字段检查、危险模式检查）
    3. 策略参数校验
    4. 生成标准化 config_preview JSON

    安全保证：
    - mode 强制固定为 "paper"
    - live_trading 强制固定为 False
    - testnet 强制固定为 False
    - 检测到 api_key/secret 等敏感字段直接拒绝
    - 检测到 mode=live/testnet/live_trading=true 直接拒绝

    本接口不调用任何 Hummingbot API 启动接口。
    """
    try:
        # 获取原始请求体（用于检查 Pydantic 未验证的额外字段）
        raw_request_data = await raw_request.json()

        # 调用 service 生成预览
        result = await generate_paper_bot_preview(
            request=paper_bot_request,
            raw_request_data=raw_request_data,
        )

        return result

    except Exception as e:
        return PaperBotPreviewResponse(
            valid=False,
            error=f"生成预览时发生错误: {str(e)}",
        )


# ── Paper Bot 启动 (v1.2.2) ───────────────────────────────────────────────────

@router.post("/paper-bots/start", response_model=PaperBotStartResponse)
async def start_paper_bot_endpoint(
    paper_bot_request: PaperBotPreviewRequest,
    raw_request: Request,
):
    """
    启动 Hummingbot Paper Bot。

    v1.2.2 阶段启动 Paper Bot，使用虚拟资金模拟运行。

    功能：
    1. 接收用户提交的 Paper Bot 配置参数
    2. 后端安全校验（敏感字段检查、危险模式检查）
    3. 策略参数校验
    4. 调用 Hummingbot API 启动 Paper Bot

    安全保证：
    - mode 强制固定为 "paper"
    - live_trading 强制固定为 False
    - testnet 强制固定为 False
    - 检测到 api_key/secret 等敏感字段直接拒绝
    - 检测到 mode=live/testnet/live_trading=true 直接拒绝
    - 不调用任何真实交易接口

    如果 Hummingbot API 当前版本不支持 Paper Bot 启动接口，返回清晰错误，不伪造成功。
    """
    try:
        # 获取原始请求体（用于检查 Pydantic 未验证的额外字段）
        raw_request_data = await raw_request.json()

        # 调用 service 启动 Paper Bot
        result = await start_paper_bot(
            request=paper_bot_request,
            raw_request_data=raw_request_data,
        )

        return result

    except Exception as e:
        return PaperBotStartResponse(
            local_record_created=False,
            remote_started=False,
            remote_confirmed=False,
            error=f"启动 Paper Bot 时发生错误: {str(e)}",
        )


# ── Paper Bot 查询接口 (v1.2.3) ────────────────────────────────────────────

@router.get("/paper-bots")
async def list_paper_bots():
    """
    获取 Paper Bot 列表。

    返回本地记录的 Paper Bot 和 Hummingbot API 中的 Bot。
    """
    try:
        result = await get_paper_bots_list()
        return result
    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": {"bots": []},
            "error": str(e),
        }


@router.get("/paper-bots/{paper_bot_id}")
async def get_paper_bot(paper_bot_id: str):
    """
    获取单个 Paper Bot 详情。
    """
    try:
        result = await get_paper_bot_detail(paper_bot_id)
        return result
    except Exception as e:
        return {
            "connected": False,
            "source": "quantagent",
            "data": None,
            "error": str(e),
        }


@router.get("/paper-bots/{paper_bot_id}/orders")
async def get_paper_bot_orders(paper_bot_id: str):
    """
    获取 Paper Bot 模拟订单。

    注意：当前 Hummingbot API 不支持按 bot_id 精确过滤，
    返回全局订单数据。
    """
    try:
        result = await svc_get_paper_bot_orders(paper_bot_id)
        return result
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


@router.get("/paper-bots/{paper_bot_id}/positions")
async def get_paper_bot_positions(paper_bot_id: str):
    """
    获取 Paper Bot 模拟持仓。

    注意：当前 Hummingbot API 不支持按 bot_id 精确过滤，
    返回全局持仓数据。
    """
    try:
        result = await svc_get_paper_bot_positions(paper_bot_id)
        return result
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


@router.get("/paper-bots/{paper_bot_id}/portfolio")
async def get_paper_bot_portfolio(paper_bot_id: str):
    """
    获取 Paper Bot 模拟资产。

    注意：当前 Hummingbot API 不支持按 bot_id 精确隔离资产，
    返回全局 Portfolio 数据。
    """
    try:
        result = await svc_get_paper_bot_portfolio(paper_bot_id)
        return result
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


@router.get("/paper-bots/{paper_bot_id}/logs")
async def get_paper_bot_logs(paper_bot_id: str):
    """
    获取 Paper Bot 日志（只读）。

    如果日志接口不可用，返回友好提示。
    """
    try:
        result = await svc_get_paper_bot_logs(paper_bot_id)
        return result
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


# ── Paper Bot 停止接口 (v1.2.4) ────────────────────────────────────────────

@router.post("/paper-bots/{paper_bot_id}/stop")
async def stop_paper_bot_endpoint(
    paper_bot_id: str,
    raw_request: Request,
):
    """
    停止 Paper Bot。

    安全规则：
    - 只允许停止 Paper Bot（mode=paper）
    - 不允许停止 Testnet / Live Bot
    - confirm 必须为 true
    - 不允许包含敏感字段
    - 不执行撤单
    - 不执行任何真实交易操作
    - 操作日志记录

    如果 Hummingbot API 当前版本不支持停止接口，返回清晰错误，不伪造成功。
    """
    try:
        raw_request_data = await raw_request.json()
    except Exception:
        raw_request_data = {}

    try:
        result = await stop_paper_bot(
            paper_bot_id=paper_bot_id,
            raw_request_data=raw_request_data,
        )
        return result
    except Exception as e:
        now = datetime.utcnow().isoformat() + "Z"
        return {
            "stopped": False,
            "source": "quantagent",
            "mode": "paper",
            "live_trading": False,
            "testnet": False,
            "data": None,
            "error": f"停止 Paper Bot 时发生错误: {str(e)}",
            "timestamp": now,
        }


# ── Paper Bot 本地资产隔离接口 (v1.3.0 Phase 3 P2-2) ──────────────────────

@router.get("/paper-bots/{paper_bot_id}/local-portfolio")
async def get_paper_bot_local_portfolio(paper_bot_id: str):
    """
    获取 Paper Bot 的本地隔离资产（独立追踪，不依赖 Hummingbot 全局 Portfolio）。

    当 Hummingbot API 的 /portfolio/state 不支持按 Bot 隔离时，
    本接口返回通过本地成交记录独立计算的资产状态。

    返回内容：
    - initial_balance: 初始资金
    - cash_balance: 当前现金余额
    - position_value: 当前持仓价值（实时价格）
    - total_equity: 总权益 = cash + position_value
    - pnl: 浮动盈亏
    - pnl_pct: 盈亏百分比
    - positions: 持仓明细
    - trade_count: 累计成交笔数
    """
    try:
        from app.services.paper_bot_local_portfolio import paper_bot_local_portfolio
        portfolio = await paper_bot_local_portfolio.get_portfolio(paper_bot_id)
        if portfolio is None:
            raise HTTPException(
                status_code=404,
                detail=f"Paper Bot '{paper_bot_id}' 未找到或未初始化本地资产追踪。"
            )
        return portfolio
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取本地资产失败: {str(e)}")


@router.get("/paper-bots/{paper_bot_id}/trade-history")
async def get_paper_bot_trade_history(
    paper_bot_id: str,
    limit: int = 50,
):
    """
    获取 Paper Bot 的本地成交历史记录。

    limit: 最大返回条数，默认 50 条
    """
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1-500 之间")

    try:
        from app.services.paper_bot_local_portfolio import paper_bot_local_portfolio
        history = await paper_bot_local_portfolio.get_trade_history(paper_bot_id, limit=limit)
        return {"paper_bot_id": paper_bot_id, "trades": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取成交历史失败: {str(e)}")


@router.get("/paper-bots/local-portfolios")
async def get_all_local_portfolios():
    """
    获取所有 Paper Bot 的本地隔离资产（多 Bot 资产隔离视图）。
    """
    try:
        from app.services.paper_bot_local_portfolio import paper_bot_local_portfolio
        portfolios = await paper_bot_local_portfolio.get_all_portfolios()
        return {"portfolios": portfolios, "count": len(portfolios)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取资产列表失败: {str(e)}")
