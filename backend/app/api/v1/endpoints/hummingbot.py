"""
Hummingbot API Endpoints (Read-only)

提供只读访问 Hummingbot API 的 REST 接口：
- GET /hummingbot/status     - API 连接状态
- GET /hummingbot/docker     - Docker 容器状态
- GET /hummingbot/connectors - Connectors 列表
- GET /hummingbot/portfolio - Portfolio 信息
- GET /hummingbot/bots       - Bots 编排状态

注意：
- 所有接口仅返回只读数据，不执行真实交易
- 不暴露 Hummingbot API 认证信息到前端
"""

from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.hummingbot_api_service import (
    get_hummingbot_service,
    HummingbotAPIError,
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
