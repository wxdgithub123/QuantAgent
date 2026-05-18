"""
Paper Bot WebSocket Manager

提供 Paper Bot 的 WebSocket 实时推送功能：
- Bot 状态更新推送
- 订单/持仓变更推送
- 心跳机制
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional, Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class PaperBotWebSocketManager:
    """Paper Bot WebSocket 连接管理器"""

    def __init__(self):
        # paper_bot_id -> set of WebSocket connections
        self._bot_connections: Dict[str, Set[WebSocket]] = {}
        # 全局连接
        self._global_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        paper_bot_id: Optional[str] = None,
    ) -> None:
        """接受 WebSocket 连接"""
        await websocket.accept()
        async with self._lock:
            if paper_bot_id:
                if paper_bot_id not in self._bot_connections:
                    self._bot_connections[paper_bot_id] = set()
                self._bot_connections[paper_bot_id].add(websocket)
                logger.info(f"WS connected for bot {paper_bot_id}. Total: {len(self._bot_connections[paper_bot_id])}")
            else:
                self._global_connections.add(websocket)
                logger.info(f"WS connected (global). Total: {len(self._global_connections)}")

    async def disconnect(
        self,
        websocket: WebSocket,
        paper_bot_id: Optional[str] = None,
    ) -> None:
        """断开 WebSocket 连接"""
        async with self._lock:
            if paper_bot_id and paper_bot_id in self._bot_connections:
                self._bot_connections[paper_bot_id].discard(websocket)
                if not self._bot_connections[paper_bot_id]:
                    del self._bot_connections[paper_bot_id]
                logger.info(f"WS disconnected for bot {paper_bot_id}")
            else:
                self._global_connections.discard(websocket)
                logger.info("WS disconnected (global)")

    async def broadcast_bot_status(
        self,
        paper_bot_id: str,
        status: Dict[str, Any],
    ) -> None:
        """广播 Bot 状态更新"""
        await self._broadcast(
            key=paper_bot_id,
            message={
                "type": "bot_status_update",
                "paper_bot_id": paper_bot_id,
                "data": status,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    async def broadcast_orders(
        self,
        paper_bot_id: str,
        orders: list,
    ) -> None:
        """广播订单更新"""
        await self._broadcast(
            key=paper_bot_id,
            message={
                "type": "orders_update",
                "paper_bot_id": paper_bot_id,
                "data": orders,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    async def broadcast_positions(
        self,
        paper_bot_id: str,
        positions: list,
    ) -> None:
        """广播持仓更新"""
        await self._broadcast(
            key=paper_bot_id,
            message={
                "type": "positions_update",
                "paper_bot_id": paper_bot_id,
                "data": positions,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    async def broadcast_portfolio(
        self,
        paper_bot_id: str,
        portfolio: Dict[str, Any],
    ) -> None:
        """广播资产更新"""
        await self._broadcast(
            key=paper_bot_id,
            message={
                "type": "portfolio_update",
                "paper_bot_id": paper_bot_id,
                "data": portfolio,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    async def broadcast_heartbeat(self) -> None:
        """广播心跳消息"""
        await self._broadcast_global(
            message={
                "type": "heartbeat",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )

    async def _broadcast(
        self,
        key: str,
        message: Dict[str, Any],
    ) -> None:
        """向特定 Bot 的所有连接广播"""
        async with self._lock:
            connections = set(self._bot_connections.get(key, set()))
            global_conns = set(self._global_connections)

        all_connections = connections | global_conns

        for ws in all_connections:
            try:
                await ws.send_json(message)
            except Exception:
                # 连接已断开，移除
                if ws in connections:
                    async with self._lock:
                        if key in self._bot_connections:
                            self._bot_connections[key].discard(ws)
                if ws in global_conns:
                    async with self._lock:
                        self._global_connections.discard(ws)

    async def _broadcast_global(
        self,
        message: Dict[str, Any],
    ) -> None:
        """向全局连接广播"""
        async with self._lock:
            connections = set(self._global_connections)

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                async with self._lock:
                    self._global_connections.discard(ws)

    def get_connection_count(self, paper_bot_id: Optional[str] = None) -> int:
        """获取连接数量"""
        if paper_bot_id and paper_bot_id in self._bot_connections:
            return len(self._bot_connections[paper_bot_id])
        return len(self._global_connections) + sum(
            len(v) for v in self._bot_connections.values()
        )


# 全局单例
paper_bot_ws_manager = PaperBotWebSocketManager()
