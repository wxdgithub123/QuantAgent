"""
Hummingbot Testnet Perpetual Bot API Endpoints

v1.3.x: Testnet 永续合约 Bot

接口：
- POST /hummingbot/testnet-bots/preview       - 配置预览
- POST /hummingbot/testnet-bots/start         - 启动 Bot
- GET  /hummingbot/testnet-bots               - Bot 列表
- GET  /hummingbot/testnet-bots/{id}          - Bot 详情
- POST /hummingbot/testnet-bots/{id}/stop     - 停止 Bot

注意：
- mode = testnet，使用测试网 API Key
- market_type = perpetual
- 不动真钱
"""

from typing import Any, Optional
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.services.hummingbot_testnet_bot_service import (
    generate_testnet_bot_preview,
    start_testnet_bot,
    get_testnet_bots_list,
    get_testnet_bot_detail,
    stop_testnet_bot,
)
from app.schemas.hummingbot_testnet_bot import (
    TestnetBotPreviewRequest,
    TestnetBotPreviewResponse,
    TestnetBotStartRequest,
    TestnetBotStartResponse,
)


router = APIRouter()


@router.post("/testnet-bots/preview", response_model=TestnetBotPreviewResponse)
async def preview_testnet_bot(request: TestnetBotPreviewRequest):
    """
    生成 Testnet Bot 配置预览。

    预览生成的 Hummingbot controller payload，验证字段合法性。
    不执行部署，不创建 Bot。
    """
    result = await generate_testnet_bot_preview(request, raw_request_data=request.model_dump())
    return result


@router.post("/testnet-bots/start", response_model=TestnetBotStartResponse)
async def start_testnet_bot_endpoint(request: TestnetBotStartRequest):
    """
    启动 Testnet Bot。

    流程：
    1. 验证 credentials_profile 存在
    2. 创建 controller config
    3. 调用 deploy-v2-controllers
    4. 验证 active_bots 出现

    验收标准：
    - active_bots 出现新 Bot
    - remote_status = running
    - can_fetch_runtime_data = true
    """
    result = await start_testnet_bot(request, raw_request_data=request.model_dump())
    return result


@router.get("/testnet-bots")
async def list_testnet_bots():
    """获取 Testnet Bot 列表"""
    result = await get_testnet_bots_list()
    return result


@router.get("/testnet-bots/{testnet_bot_id}")
async def get_testnet_bot(testnet_bot_id: str):
    """获取 Testnet Bot 详情"""
    result = await get_testnet_bot_detail(testnet_bot_id)
    return result


@router.post("/testnet-bots/{testnet_bot_id}/stop")
async def stop_testnet_bot_endpoint(testnet_bot_id: str, body: Optional[dict] = Body(None)):
    """
    停止 Testnet Bot。

    必须包含 confirm=true。
    """
    result = await stop_testnet_bot(testnet_bot_id, raw_request_data=body or {})
    return result
