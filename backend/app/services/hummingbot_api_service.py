"""
Hummingbot API Service (Read-only Integration)

提供只读访问 Hummingbot API 的能力：
- 连接状态查询
- Docker 容器状态
- Connectors 列表
- Portfolio 信息
- Bots 编排状态

注意：
- 本模块仅实现只读接口，不执行真实交易
- 如果 QuantAgent 运行在 Docker 中，HUMMINGBOT_API_URL 需要改成 http://host.docker.internal:8000
"""

import httpx
from typing import Any, Dict, Optional, List
from app.core.config import settings


class HummingbotAPIError(Exception):
    """Hummingbot API 异常基类"""
    def __init__(self, message: str, status_code: Optional[int] = None, detail: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class HummingbotAPIService:
    """
    Hummingbot API 只读客户端

    支持 Basic Auth（当 username 和 password 都存在时使用）
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.HUMMINGBOT_API_URL).rstrip("/")
        self.timeout = timeout or settings.HUMMINGBOT_API_TIMEOUT

        # 从 settings 读取认证信息（如果未传入参数）
        username = username or settings.HUMMINGBOT_API_USERNAME
        password = password or settings.HUMMINGBOT_API_PASSWORD

        # 构建认证（当 username 和 password 都存在时使用）
        self._auth = None
        if username and password:
            self._auth = httpx.BasicAuth(username, password)

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        统一请求封装

        Args:
            method: HTTP 方法
            path: API 路径（相对于 base_url）
            json: 请求体
            params: 查询参数

        Returns:
            API 返回的 JSON 数据

        Raises:
            HummingbotAPIError: API 调用失败时抛出
        """
        url = f"{self.base_url}/{path.lstrip('/')}"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,  # 允许跟随重定向
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    auth=self._auth,
                )

                # 处理不同状态码
                if response.status_code == 401:
                    raise HummingbotAPIError(
                        "Hummingbot API 认证失败，请检查 HUMMINGBOT_API_USERNAME 和 HUMMINGBOT_API_PASSWORD",
                        status_code=401,
                    )
                elif response.status_code == 404:
                    raise HummingbotAPIError(
                        f"Hummingbot API 路径 {path} 不存在（404）。"
                        " 接口路径可能与当前 Hummingbot 版本不一致，请以 Swagger 文档 http://localhost:8000/docs 为准。",
                        status_code=404,
                    )
                elif not response.is_success:
                    raise HummingbotAPIError(
                        f"Hummingbot API 请求失败: HTTP {response.status_code}",
                        status_code=response.status_code,
                        detail=response.text[:500] if response.text else None,
                    )

                # 尝试解析 JSON
                try:
                    return response.json()
                except Exception:
                    # 如果不是 JSON，返回原始文本
                    return {"_raw": response.text}

        except httpx.ConnectError:
            raise HummingbotAPIError(
                f"Hummingbot API 无法连接（{self.base_url}）。"
                " 请确保 Hummingbot API 已启动并且地址配置正确。"
            )
        except httpx.TimeoutException:
            raise HummingbotAPIError(
                f"Hummingbot API 请求超时（{self.timeout}秒）。"
                " 请检查 Hummingbot 服务是否响应正常。"
            )
        except HummingbotAPIError:
            raise
        except Exception as e:
            raise HummingbotAPIError(f"Hummingbot API 未知错误: {str(e)}")

    async def get_status(self) -> Dict[str, Any]:
        """获取 Hummingbot API 状态"""
        return await self._request("GET", "/")

    async def get_docker_running(self) -> Dict[str, Any]:
        """获取运行中的 Docker 容器"""
        return await self._request("GET", "/docker/running")

    async def get_active_containers(self) -> Dict[str, Any]:
        """获取活跃容器列表"""
        return await self._request("GET", "/docker/active-containers")

    async def get_connectors(self) -> Dict[str, Any]:
        """获取支持的 connectors 列表"""
        return await self._request("GET", "/connectors")

    async def get_portfolio_state(self) -> Dict[str, Any]:
        """
        获取 portfolio 状态

        使用 POST /portfolio/state 接口，支持过滤条件。
        如果返回 404，说明当前 Hummingbot API 版本不支持此接口。
        """
        return await self._request("POST", "/portfolio/state", json={})

    async def get_accounts(self) -> Dict[str, Any]:
        """
        获取账户列表

        使用 GET /accounts/ 接口。
        """
        return await self._request("GET", "/accounts/")

    async def get_bots(self) -> Dict[str, Any]:
        """
        获取 bots 编排状态

        优先请求 /bot-orchestration/status 获取活跃 bots 状态。
        如果返回 404，调用者需要降级处理（使用 active containers 作为备选数据源）。
        """
        return await self._request("GET", "/bot-orchestration/status")

    async def get_bots_mqtt(self) -> Dict[str, Any]:
        """
        获取 MQTT 连接状态和发现的 bots

        如果 /bot-orchestration/status 返回 404，这个接口可能也不可用。
        """
        return await self._request("GET", "/bot-orchestration/mqtt")

    async def get_active_orders(self) -> Dict[str, Any]:
        """
        获取活跃订单

        使用 POST /trading/orders/active 接口。
        返回当前正在进行的订单（未完成/未取消）。
        """
        return await self._request("POST", "/trading/orders/active", json={})

    async def search_orders(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        搜索历史订单

        使用 POST /trading/orders/search 接口，支持过滤条件：
        - account_names: 账户列表
        - connector_names: 连接器列表
        - trading_pair: 交易对
        - side: BUY/SELL
        - order_type: 订单类型
        - status: 订单状态
        - start_time: 开始时间戳
        - end_time: 结束时间戳
        """
        return await self._request("POST", "/trading/orders/search", json=filters or {})

    async def get_positions(self) -> Dict[str, Any]:
        """
        获取持仓信息

        使用 POST /trading/positions 接口。
        返回当前开仓的永续合约持仓。
        """
        return await self._request("POST", "/trading/positions", json={})

    async def get_trades(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取交易历史

        使用 POST /trading/trades 接口。
        支持过滤条件来查询历史成交记录。
        """
        return await self._request("POST", "/trading/trades", json=filters or {})


# 全局单例（延迟初始化）
_hummingbot_service: Optional[HummingbotAPIService] = None


def get_hummingbot_service() -> HummingbotAPIService:
    """获取 Hummingbot API Service 单例"""
    global _hummingbot_service
    if _hummingbot_service is None:
        _hummingbot_service = HummingbotAPIService()
    return _hummingbot_service
