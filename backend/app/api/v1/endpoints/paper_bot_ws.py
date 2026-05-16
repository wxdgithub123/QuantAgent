"""
Paper Bot WebSocket Endpoint

提供 Paper Bot 的 WebSocket 实时推送接口：
- WS /ws/paper-bots            - 全局订阅（所有 Bot 更新）
- WS /ws/paper-bots/{id}       - 单个 Bot 订阅

消息类型：
- bot_status_update    - Bot 状态变更
- orders_update       - 订单更新
- positions_update    - 持仓更新
- portfolio_update    - 资产更新
- heartbeat          - 心跳（每30秒）
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.websocket.paper_bot_ws import paper_bot_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/paper-bots")
async def ws_paper_bots_global(websocket: WebSocket):
    """
    WebSocket 全局订阅（所有 Bot 更新）。

    连接后持续接收：
    - 所有 Bot 的状态更新
    - 全局心跳
    """
    await paper_bot_ws_manager.connect(websocket, paper_bot_id=None)
    try:
        while True:
            # 保持连接，接收客户端消息（目前无用途，预留）
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                logger.debug(f"WS global received: {data}")
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await paper_bot_ws_manager.disconnect(websocket, paper_bot_id=None)


@router.websocket("/ws/paper-bots/{paper_bot_id}")
async def ws_paper_bots_single(
    websocket: WebSocket,
    paper_bot_id: str,
):
    """
    WebSocket 单个 Bot 订阅。

    连接后持续接收：
    - 该 Bot 的状态更新
    - 该 Bot 的订单/持仓/资产更新
    - 全局心跳
    """
    await paper_bot_ws_manager.connect(websocket, paper_bot_id=paper_bot_id)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                logger.debug(f"WS {paper_bot_id} received: {data}")
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await paper_bot_ws_manager.disconnect(websocket, paper_bot_id=paper_bot_id)
